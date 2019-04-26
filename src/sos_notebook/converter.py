#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import argparse
import re
import sys
import time
from io import StringIO
from queue import Empty

import nbformat
from nbconvert.exporters import Exporter
from nbconvert.preprocessors.execute import ExecutePreprocessor, CellExecutionError
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook, output_from_msg

from sos.converter import extract_workflow
from sos.syntax import SOS_SECTION_HEADER
from sos.utils import env

#
# Converter from Notebook
#


def get_notebook_to_script_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.ipynb FILE.sos (or --to sos)',
        description='''Export Jupyter notebook with a SoS kernel to a
        .sos file. The cells are presented in the .sos file as
        cell structure lines, which will be ignored if executed
        in batch mode ''')
    return parser


# This class cannot be defined in .kernel because it would cause some
# weird problem with unittesting not able to resolve __main__
class SoS_Exporter(Exporter):

    def __init__(self, config=None, **kwargs):
        self.output_extension = '.sos'
        self.output_mimetype = 'text/x-sos'
        Exporter.__init__(self, config, **kwargs)

    def from_notebook_cell(self, cell, fh, idx=0):
        # in non-all mode, markdown cells are ignored because they can be mistakenly
        # treated as markdown content of an action or script #806
        if cell.cell_type != "code":
            return
        #
        # Non-sos code cells are also ignored
        if 'kernel' in cell.metadata and cell.metadata['kernel'] not in ('sos',
                                                                         'SoS',
                                                                         None):
            return
        lines = cell.source.split('\n')
        valid_cell = False
        for idx, line in enumerate(lines):
            if valid_cell or (line.startswith('%include') or
                              line.startswith('%from')):
                fh.write(line + '\n')
            elif SOS_SECTION_HEADER.match(line):
                valid_cell = True
                # look retrospectively for comments
                c = idx - 1
                comment = ''
                while c >= 0 and lines[c].startswith('#'):
                    comment = lines[c] + '\n' + comment
                    c -= 1
                fh.write(comment + line + '\n')
            # other content, namely non-%include lines before section header is ignored
        if valid_cell:
            fh.write('\n')
        return idx

    def from_notebook_node(self, nb, resources, **kwargs):
        #
        cells = nb.cells
        with StringIO() as fh:
            fh.write('#!/usr/bin/env sos-runner\n')
            fh.write('#fileformat=SOS1.0\n\n')
            idx = 0
            for cell in cells:
                idx = self.from_notebook_cell(cell, fh, idx)
            content = fh.getvalue()
        resources['output_extension'] = '.sos'
        return content, resources


def notebook_to_script(notebook_file, sos_file, args=None, unknown_args=None):
    '''
    Convert a ipython notebook to sos format.
    '''
    if unknown_args:
        raise ValueError(f'Unrecognized parameter {unknown_args}')
    exporter = SoS_Exporter()
    notebook = nbformat.read(notebook_file, nbformat.NO_CONVERT)
    output, _ = exporter.from_notebook_node(notebook, {})
    if not sos_file:
        sys.stdout.write(output)
    elif isinstance(sos_file, str):
        with open(sos_file, 'w') as sos:
            sos.write(output)
        env.logger.info(f'SoS script saved to {sos_file}')
    else:
        sos_file.write(output)


#
# Converter to Notebook
#


def get_script_to_notebook_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.sos FILE._ipynb (or --to ipynb)',
        description='''Convert a sos script to Jupyter notebook (.ipynb)
            so that it can be opened by Jupyter notebook.''')
    return parser


def add_cell(cells, content, cell_type, cell_count, metainfo):
    # if a section consist of all report, report it as a markdown cell
    if not content:
        return
    if cell_type not in ('code', 'markdown'):
        env.logger.warning(f'Unrecognized cell type {cell_type}, code assumed.')
    if cell_type == 'markdown' and any(
            x.strip() and not x.startswith('#! ') for x in content):
        env.logger.warning(
            'Markdown lines not starting with #!, code cell assumed.')
        cell_type = 'code'
    #
    if cell_type == 'markdown':
        cells.append(
            new_markdown_cell(
                source=''.join([x[3:] for x in content]).strip(),
                metadata=metainfo))
    else:
        cells.append(
            new_code_cell(
                # remove any trailing blank lines...
                source=''.join(content).strip(),
                execution_count=cell_count,
                metadata=metainfo))


class SoS_ExecutePreprocessor(ExecutePreprocessor):

    def __init__(self, filename, *args, **kwargs):
        super(SoS_ExecutePreprocessor, self).__init__(*args, **kwargs)
        self._filename = filename

    def _prepare_meta(self, cell):
        meta = {}
        run_notebook = re.search(
            r'^%sosrun($|\s)|^%sossave($|\s)|^%preview\s.*(-w|--workflow).*$',
            cell.source, re.MULTILINE)
        if run_notebook:
            meta['workflow'] = self._workflow
        if re.search(r'^%toc\s/', cell.source, re.MULTILINE):
            meta['toc'] = self._toc
        meta['path'] = self._filename
        meta['use_panel'] = False
        meta['rerun'] = False
        # ID is dynamically generated by the frontend and does not exist
        # in the backend for batch mode
        meta['cell_id'] = 0
        meta['batch_mode'] = True
        meta['cell_kernel'] = cell.metadata.kernel
        return meta

    def run_cell(self, cell, cell_index=0):
        # sos is the additional meta information sent to kernel
        content = dict(
            code=cell.source,
            silent=False,
            store_history=False,
            user_expressions='',
            allow_stdin=False,
            stop_on_error=False,
            sos=self._prepare_meta(cell))
        msg = self.kc.session.msg('execute_request', content)
        self.kc.shell_channel.send(msg)
        msg_id = msg['header']['msg_id']

        # the reset is copied from https://github.com/jupyter/nbconvert/blob/master/nbconvert/preprocessors/execute.py
        # because we only need to change the first line

        #  msg_id = self.kc.execute(cell.source)

        self.log.debug("Executing cell:\n%s", cell.source)
        exec_reply = self._wait_for_reply(msg_id, cell)

        outs = cell.outputs = []

        while True:
            try:
                # We've already waited for execute_reply, so all output
                # should already be waiting. However, on slow networks, like
                # in certain CI systems, waiting < 1 second might miss messages.
                # So long as the kernel sends a status:idle message when it
                # finishes, we won't actually have to wait this long, anyway.
                msg = self.kc.iopub_channel.get_msg(timeout=self.iopub_timeout)
            except Empty:
                self.log.warning("Timeout waiting for IOPub output")
                if self.raise_on_iopub_timeout:
                    raise RuntimeError("Timeout waiting for IOPub output")
                else:
                    break
            if msg['parent_header'].get('msg_id') != msg_id:
                # not an output from our execution
                continue

            msg_type = msg['msg_type']
            self.log.debug("output: %s", msg_type)
            content = msg['content']

            # set the prompt number for the input and the output
            if 'execution_count' in content:
                cell['execution_count'] = content['execution_count']

            if msg_type == 'status':
                if content['execution_state'] == 'idle':
                    break
                else:
                    continue
            elif msg_type == 'execute_input':
                continue
            elif msg_type == 'clear_output':
                outs[:] = []
                # clear display_id mapping for this cell
                for display_id, cell_map in self._display_id_map.items():
                    if cell_index in cell_map:
                        cell_map[cell_index] = []
                continue
            elif msg_type.startswith('comm'):
                continue

            display_id = None
            if msg_type in {
                    'execute_result', 'display_data', 'update_display_data'
            }:
                display_id = msg['content'].get('transient',
                                                {}).get('display_id', None)
                if display_id:
                    self._update_display_id(display_id, msg)
                if msg_type == 'update_display_data':
                    # update_display_data doesn't get recorded
                    continue

            try:
                out = output_from_msg(msg)
            except ValueError:
                self.log.error("unhandled iopub msg: " + msg_type)
                continue
            if display_id:
                # record output index in:
                #   _display_id_map[display_id][cell_idx]
                cell_map = self._display_id_map.setdefault(display_id, {})
                output_idx_list = cell_map.setdefault(cell_index, [])
                output_idx_list.append(len(outs))

            outs.append(out)

        return exec_reply, outs

    def _scan_table_of_content(self, nb):
        cells = nb.cells
        TOC = ''
        for cell in cells:
            if cell.cell_type == "markdown":
                for line in cell.source.splitlines():
                    if re.match('^#+ ', line):
                        TOC += line + '\n'
        return TOC

    def preprocess(self, nb, *args, **kwargs):
        self._workflow = extract_workflow(nb)
        self._toc = self._scan_table_of_content(nb)
        return super(SoS_ExecutePreprocessor,
                     self).preprocess(nb, *args, **kwargs)


def script_to_notebook(script_file, notebook_file, args=None,
                       unknown_args=None):
    '''
    Convert a sos script to iPython notebook (.ipynb) so that it can be opened
    by Jupyter notebook.
    '''
    if unknown_args:
        raise ValueError(f'Unrecognized parameter {unknown_args}')
    cells = []
    cell_count = 1
    cell_type = 'code'
    metainfo = {}
    content = []

    with open(script_file) as script:
        first_block = True
        for line in script:
            if line.startswith('#') and first_block:
                if line.startswith('#!'):
                    continue
                if line.startswith('#fileformat='):
                    if not line[12:].startswith('SOS'):
                        raise RuntimeError(
                            f'{script_file} is not a SoS script according to #fileformat line.'
                        )
                    continue

            first_block = False

            mo = SOS_SECTION_HEADER.match(line)
            if mo:
                # get rid of empty content
                if not any(x.strip() for x in content):
                    content = []

                if content:
                    # the comment should be absorbed into the next section
                    i = len(content) - 1
                    while i >= 0 and content[i].startswith('#'):
                        i -= 1
                    # i point to the last non comment line
                    if i >= 0:
                        add_cell(cells, content[:i + 1], cell_type, cell_count,
                                 metainfo)
                    content = content[i + 1:]

                cell_type = 'code'
                cell_count += 1
                metainfo = {'kernel': 'SoS'}
                content += [line]
                continue

            if line.startswith('#!'):
                if cell_type == 'markdown':
                    content.append(line)
                    continue
                else:
                    # get ride of empty content
                    if not any(x.strip() for x in content):
                        content = []

                    if content:
                        add_cell(cells, content, cell_type, cell_count,
                                 metainfo)

                    cell_type = 'markdown'
                    cell_count += 1
                    content = [line]
                    continue

            # other cases
            content.append(line)
    #
    if content and any(x.strip() for x in content):
        add_cell(cells, content, cell_type, cell_count, metainfo)
    #
    nb = new_notebook(
        cells=cells,
        metadata={
            'kernelspec': {
                "display_name": "SoS",
                "language": "sos",
                "name": "sos"
            },
            "language_info": {
                'codemirror_mode': 'sos',
                "file_extension": ".sos",
                "mimetype": "text/x-sos",
                "name": "sos",
                "pygments_lexer": "python",
                'nbconvert_exporter': 'sos_notebook.converter.SoS_Exporter',
            },
            'sos': {
                'kernels': [['SoS', 'sos', '', '']]
            }
        })
    if not notebook_file:
        nbformat.write(nb, sys.stdout, 4)
    else:
        with open(notebook_file, 'w') as notebook:
            nbformat.write(nb, notebook, 4)
        env.logger.info(f'Jupyter notebook saved to {notebook_file}')
    # if err:
    #    raise RuntimeError(repr(err))


#
# notebook to HTML
#


def export_notebook(exporter_class,
                    to_format,
                    notebook_file,
                    output_file,
                    unknown_args=None,
                    view=False):

    import os
    import subprocess
    if not os.path.isfile(notebook_file):
        raise RuntimeError(f'{notebook_file} does not exist')
    cfg_file = os.path.join(os.path.expanduser('~'), '.sos', 'nbconfig.py')
    if not os.path.isfile(cfg_file):
        with open(cfg_file, 'w') as cfg:
            cfg.write(f'''
import os
import sos
import sos_notebook

c = get_config()
c.TemplateExporter.template_path.extend([
  os.path.join(os.path.split(os.path.abspath(sos.__file__))[0], 'templates'),
  os.path.join(os.path.split(os.path.abspath(sos_notebook.__file__))[0], 'templates')])
''')
    if not output_file:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix='.' + to_format).name
        tmp_stderr = tempfile.NamedTemporaryFile(
            delete=False, suffix='.' + to_format).name
        with open(tmp_stderr, 'w') as err:
            ret = subprocess.call(
                [
                    'jupyter', 'nbconvert', notebook_file, '--to', to_format,
                    '--output', tmp, '--config', cfg_file
                ] + ([] if unknown_args is None else unknown_args),
                stderr=err)
        with open(tmp_stderr) as err:
            err_msg = err.read()
        if ret != 0:
            env.logger.error(err_msg)
            env.logger.error(
                f'Failed to convert {notebook_file} to {to_format} format')
        else:
            # identify output files
            dest_file = err_msg.rsplit()[-1]
            if not os.path.isfile(dest_file):
                env.logger.error(err_msg)
                env.logger.error('Failed to get converted file.')
            elif view:
                import webbrowser
                url = f'file://{os.path.abspath(dest_file)}'
                env.logger.info(f'Viewing {url} in a browser')
                webbrowser.open(url, new=2)
                # allow browser some time to process the file before this process removes it
                time.sleep(2)
            else:
                with open(dest_file, 'rb') as tfile:
                    sys.stdout.buffer.write(tfile.read())
        try:
            os.remove(tmp)
        except Exception:
            pass
    else:
        ret = subprocess.call([
            'jupyter', 'nbconvert',
            os.path.abspath(notebook_file), '--to', to_format, '--output',
            os.path.abspath(output_file), '--config', cfg_file
        ] + ([] if unknown_args is None else unknown_args))
        if ret != 0:
            env.logger.error(
                f'Failed to convert {notebook_file} to {to_format} format')
        else:
            env.logger.info(f'Output saved to {output_file}')


def get_notebook_to_html_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.ipynb FILE.html (or --to html)',
        description='''Export Jupyter notebook with a SoS kernel to a
        .html file. Additional command line arguments are passed directly to
        command "jupyter nbconvert --to html" so please refer to nbconvert manual for
        available options.''')
    parser.add_argument(
        '--template',
        help='''Template to export Jupyter notebook with sos kernel. SoS provides a number
        of templates, with sos-report displays markdown cells and only output of cells with
        prominent tag, and a control panel to control the display of the rest of the content
        ''')
    parser.add_argument(
        '-e',
        '--execute',
        action='store_true',
        help='''Execute the notebook in batch mode (as if running "Cell -> Run All"
                          from Jupyter notebook interface before converting to HTML'''
    )
    parser.add_argument(
        '-v',
        '--view',
        action='store_true',
        help='''Open the output file in a broswer. In case no html file is specified,
        this option will display the HTML file in a browser, instead of writing its
        content to standard output.''')
    return parser


def notebook_to_html(notebook_file, output_file, sargs=None, unknown_args=None):
    from nbconvert.exporters.html import HTMLExporter
    import os
    if unknown_args is None:
        unknown_args = []
    if sargs and sargs.execute:
        # the step can take long time to complete
        ep = SoS_ExecutePreprocessor(notebook_file, timeout=60000)
        try:
            nb = nbformat.read(notebook_file, nbformat.NO_CONVERT)
            ep.preprocess(nb, {'metadata': {'path': '.'}})
            tmp_file = os.path.join(env.temp_dir,
                                    os.path.basename(notebook_file))
            with open(tmp_file, 'w') as tmp_nb:
                nbformat.write(nb, tmp_nb, 4)
            notebook_file = tmp_file
        except CellExecutionError as e:
            env.logger.error(f'Failed to execute notebook: {e}')
    if sargs.template:
        unknown_args = [
            '--template',
            os.path.abspath(sargs.template)
            if os.path.isfile(sargs.template) else sargs.template
        ] + unknown_args
    export_notebook(
        HTMLExporter,
        'html',
        notebook_file,
        output_file,
        unknown_args,
        view=sargs.view)


def get_notebook_to_pdf_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.ipynb FILE.pdf (or --to pdf)',
        description='''Export Jupyter notebook with a SoS kernel to a
        .pdf file. Additional command line arguments are passed directly to
        command "jupyter nbconvert --to pdf" so please refer to nbconvert manual for
        available options.''')
    parser.add_argument(
        '--template',
        help='''Template to export Jupyter notebook with sos kernel. SoS provides a number
        of templates, with sos-report displays markdown cells and only output of cells with
        prominent tag, and a control panel to control the display of the rest of the content
        ''')
    return parser


def notebook_to_pdf(notebook_file, output_file, sargs=None, unknown_args=None):
    from nbconvert.exporters.pdf import PDFExporter
    import os
    if unknown_args is None:
        unknown_args = []
    if sargs.template:
        unknown_args = [
            '--template',
            os.path.abspath(sargs.template)
            if os.path.isfile(sargs.template) else sargs.template
        ] + unknown_args
    # jupyter convert will add extension to output file...
    if output_file is not None and output_file.endswith('.pdf'):
        output_file = output_file[:-4]
    export_notebook(PDFExporter, 'pdf', notebook_file, output_file,
                    unknown_args)


def get_notebook_to_md_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.ipynb FILE.md (or --to md)',
        description='''Export Jupyter notebook with a SoS kernel to a
        markdown file. Additional command line arguments are passed directly to
        command "jupyter nbconvert --to markdown" so please refer to nbconvert manual for
        available options.''')
    return parser


def notebook_to_md(notebook_file, output_file, sargs=None, unknown_args=None):
    from nbconvert.exporters.markdown import MarkdownExporter
    export_notebook(
        MarkdownExporter, 'markdown', notebook_file, output_file,
        unknown_args if '--template' in unknown_args else
        ['--template', 'sos-markdown'] + unknown_args)


def get_notebook_to_notebook_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.ipynb FILE.ipynb (or --to ipynb)',
        description='''Export a Jupyter notebook with a non-SoS kernel to a
        SoS notebook with SoS kernel, or from a SoS notebook to a regular notebook with specified kernel.'''
    )
    parser.add_argument(
        '-k',
        '--kernel',
        default='sos',
        help='''Kernel for the destination notebook. The default kernel is
        SoS which converts a non-SoS notebook to SoS Notebook. If another kernel is specified,
        this command will remove cell-specific kernel information and convert a SoS Notebook
        to regular notebook with specified kernel.''')
    parser.add_argument(
        '--python3-to-sos',
        action='store_true',
        help='''Convert python3 cells to SoS.''')
    parser.add_argument(
        '--inplace',
        action='store_true',
        help='''Overwrite input notebook with the output.''')
    return parser


def nonSoS_to_SoS_notebook(notebook, args):
    '''Converting a nonSoS notebook to SoS notebook by adding kernel metadata'''
    # get the kernel of the notebook
    # this is like 'R', there is another 'display_name'
    lan_name = notebook['metadata']['kernelspec']['language']
    # this is like 'ir'
    kernel_name = notebook['metadata']['kernelspec']['name']

    # if it is already a SoS notebook, do nothing.
    if kernel_name == 'sos':
        if args.inplace:
            return
        env.logger.warning(
            f'Notebook is already using the sos kernel. No conversion is needed.'
        )
        return notebook

    # convert to?
    if kernel_name == 'python3' and args.python3_to_sos:
        to_lan = 'SoS'
        to_kernel = 'sos'
    else:
        to_lan = lan_name
        to_kernel = kernel_name
    #
    cells = []
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.metadata['kernel'] = to_lan
        cells.append(cell)
    #
    # new header
    metadata = {
        'kernelspec': {
            "display_name": "SoS",
            "language": "sos",
            "name": "sos"
        },
        "language_info": {
            "file_extension": ".sos",
            "mimetype": "text/x-sos",
            "name": "sos",
            "pygments_lexer": "python",
            'nbconvert_exporter': 'sos_notebook.converter.SoS_Exporter',
        },
        'sos': {
            'kernels':
                [['SoS', 'sos', '', '', '']] +
                ([[to_lan, to_kernel, '', '', '']] if to_lan != 'SoS' else [])
        }
    }
    return new_notebook(cells=cells, metadata=metadata)


def SoS_to_nonSoS_notebook(notebook, args):
    kernel_name = notebook['metadata']['kernelspec']['name']

    if kernel_name != 'sos':
        raise ValueError(
            f'Cannot convert a notebook with kernel {kernel_name} to a notebook with kernel {args.kernel}'
        )

    all_subkernels = [
        x[1] for x in notebook['metadata']['sos']['kernels'] if x[1] != 'sos'
    ]
    kinfo = [
        x for x in notebook['metadata']['sos']['kernels'] if x[1] == args.kernel
    ]
    if not kinfo:
        if args.kernel == 'python3':
            # converting SoS cells to python3, should be more or less ok
            kinfo = [[
                'Python3', 'python3', 'Python3', '', {
                    "name": "ipython",
                    "version": 3
                }
            ]]
        else:
            raise ValueError(
                f'Specified kernel {args.kernel} is not one of the subkernels ({", ".join(all_subkernels)}) used in the SoS notebook. '
            )
    if len(all_subkernels) > 1:
        env.logger.warning(
            f'More than one subkernels ({", ".join(all_subkernels)}) are used in the SoS notebook. They will all be considered as {args.kernel} cells.'
        )

    # from SoS to args.kernel, we will need to first strip the cell-level kernel info
    cells = []
    for cell in notebook.cells:
        if cell.cell_type == 'code':
            cell.metadata.pop('kernel')
        cells.append(cell)

    # NOTE: we do not have enough information to restore language_info
    # which contains things such as codemirros mode and mimetype. However,
    # Jupyter should be able to open the notebook and retrieve such information
    # from the kernel, and langauge_info will be written if the notebook is
    # saved again.
    metadata = {
        "kernelspec": {
            "display_name": kinfo[0][0],
            "language": kinfo[0][2],
            "name": kinfo[0][1]
        }
    }
    return new_notebook(cells=cells, metadata=metadata)


def notebook_to_notebook(notebook_file,
                         output_file,
                         sargs=None,
                         unknown_args=None):
    notebook = nbformat.read(notebook_file, nbformat.NO_CONVERT)
    # if we are converting to a SoS Notebook.
    if sargs.kernel in ('sos', 'SoS'):
        nb = nonSoS_to_SoS_notebook(notebook, sargs)
    else:
        nb = SoS_to_nonSoS_notebook(notebook, sargs)

    if nb is None:
        # nothing to do (e.g. sos -> sos)
        return

    if sargs.inplace:
        with open(notebook_file, 'w') as new_nb:
            nbformat.write(nb, new_nb, 4)
        env.logger.info(f'Jupyter notebook saved to {notebook_file}')
    elif not output_file:
        nbformat.write(nb, sys.stdout, 4)
    else:
        with open(output_file, 'w') as new_nb:
            nbformat.write(nb, new_nb, 4)
        env.logger.info(f'Jupyter notebook saved to {output_file}')


def get_Rmarkdown_to_notebook_parser():
    parser = argparse.ArgumentParser(
        'sos convert FILE.Rmd FILE.ipynb (or --to ipynb)',
        description='''Export a Rmarkdown file kernel to a SoS notebook. It currently
        only handles code block and Markdown, and not inline expression.''')
    return parser


def Rmarkdown_to_notebook(rmarkdown_file,
                          output_file,
                          sargs=None,
                          unknown_args=None):
    #
    with open(rmarkdown_file) as script:
        content = script.read()
    #
    # identify the headers
    header = header = re.compile('^(#+\s.*$)', re.M)
    paragraphs = re.split(header, content)
    #
    cells = []
    cell_count = 1
    for idx, p in enumerate(paragraphs):
        if idx % 2 == 1:
            # this is header, let us create a markdown cell
            cells.append(new_markdown_cell(source=p.strip()))
        else:
            # this is unknown yet, let us find ```{} block
            code = re.compile('^\s*(```{.*})$', re.M)
            endcode = re.compile('^\s*```$', re.M)

            for pidx, pc in enumerate(re.split(code, p)):
                if pidx == 0:
                    # piece before first code block. it might contain
                    # inline expression
                    cells.append(new_markdown_cell(source=pc.strip()))
                elif pidx % 2 == 0:
                    # this is AFTER the {r} piece, let us assume all R code
                    # for now
                    # this is code, but it should end somewhere
                    pieces = re.split(endcode, pc)
                    # I belive that we should have
                    #   pieces[0] <- code
                    #   pieces[1] <- rest...
                    # but I could be wrong.
                    cells.append(
                        new_code_cell(
                            source=pieces[0],
                            execution_count=cell_count,
                            metadata={'kernel': 'R'}))
                    cell_count += 1
                    #
                    for piece in pieces[1:]:
                        cells.append(new_markdown_cell(source=piece.strip()))
    #
    # create header
    nb = new_notebook(
        cells=cells,
        metadata={
            'kernelspec': {
                "display_name": "SoS",
                "language": "sos",
                "name": "sos"
            },
            "language_info": {
                "file_extension": ".sos",
                "mimetype": "text/x-sos",
                "name": "sos",
                "pygments_lexer": "python",
                'nbconvert_exporter': 'sos_notebook.converter.SoS_Exporter',
            },
            'sos': {
                'kernels': [['SoS', 'sos', '', ''], ['R', 'ir', '', '']],
                'default_kernel': 'R'
            }
        })

    if not output_file:
        nbformat.write(nb, sys.stdout, 4)
    else:
        with open(output_file, 'w') as new_nb:
            nbformat.write(nb, new_nb, 4)
        env.logger.info(f'Jupyter notebook saved to {output_file}')
