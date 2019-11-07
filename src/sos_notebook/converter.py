#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import argparse
import re
import sys
import time
import yaml
from io import StringIO

import nbformat
from nbconvert.exporters import Exporter
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

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

    def add_cell(cells, content, cell_type, cell_count, metainfo):
        # if a section consist of all report, report it as a markdown cell
        if not content:
            return
        if cell_type not in ('code', 'markdown'):
            env.logger.warning(
                f'Unrecognized cell type {cell_type}, code assumed.')
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
        '-e', '--execute', action='store_true', help='''Deprecated''')
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
        env.logger.warning(
            'Option --execute is deprecated. Please use sos-papermill instead.')
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
    cells = []
    code_count = 1

    #
    with open(rmarkdown_file) as script:
        rmdlines = script.readlines()

    def add_cell(cells, content, cell_type, metainfo):
        nonlocal code_count
        # if a section consist of all report, report it as a markdown cell
        if not content:
            return
        if cell_type not in ('code', 'markdown'):
            env.logger.warning(
                f'Unrecognized cell type {cell_type}, code assumed.')
        #
        if cell_type == 'code':
            cells.append(
                new_code_cell(
                    # remove any trailing blank lines...
                    source=''.join(content).strip(),
                    execution_count=code_count,
                    metadata=metainfo))
            code_count += 1
        elif metainfo.get('kernel', '') == 'Markdown':
            # markdown code with inline expression
            cells.append(
                new_code_cell(
                    # remove any trailing blank lines...
                    source=f'%expand `r ` --in R\n' + ''.join(content).strip(),
                    execution_count=code_count,
                    metadata=metainfo))
            code_count += 1
        else:
            cells.append(
                new_markdown_cell(
                    source=''.join(content).strip(), metadata=metainfo))

    Rmd_header = {}
    # YAML front matter appears to be restricted to strictly ---\nYAML\n---
    re_yaml_delim = re.compile(r"^---\s*$")
    delim_lines = [i for i, l in enumerate(rmdlines) if re_yaml_delim.match(l)]
    if len(delim_lines) >= 2 and delim_lines[1] - delim_lines[0] > 1:
        yamltext = '\n'.join(rmdlines[delim_lines[0] + 1:delim_lines[1]])
        try:
            Rmd_header = yaml.safe_load(yamltext)
        except yaml.YAMLError as e:
            env.logger.warning(f"Error reading document metadata block: {e}")
            env.logger.warning("Trying to continue without header")
        rmdlines = rmdlines[:delim_lines[0]] + rmdlines[delim_lines[1] + 1:]

    # the behaviour of rmarkdown appears to be that a code block does not
    # have to have matching numbers of start and end `s - just >=3
    # and there can be any number of spaces before the {r, meta} block,
    # but "r" must be the first character of that block

    re_code_start = re.compile(r"^````*\s*{r(.*)}\s*$")
    re_code_end = re.compile(r"^````*\s*$")
    re_code_inline = re.compile(r"`r.+`")

    MD, CODE = range(2)

    state = MD
    celldata = []
    meta = {}
    has_inline_markdown = False

    for l in rmdlines:
        if state == MD:
            match = re_code_start.match(l)
            if match:
                state = CODE
                # only add MD cells with non-whitespace content
                if any([c.strip() for c in celldata]):
                    add_cell(cells, celldata, 'markdown', metainfo=meta)

                celldata = []
                meta = {'kernel': 'R'}

                if match.group(1):
                    chunk_opts = match.group(1).strip(" ,")
                    if chunk_opts:
                        meta['Rmd_chunk_options'] = chunk_opts
                        if 'include=FALSE' in chunk_opts or 'echo=FALSE' in chunk_opts:
                            if 'jupyter' in meta:
                                meta['jupyter']['source_hidden'] = True
                            else:
                                meta["jupyter"] = {"source_hidden": True}
                        if 'include=FALSE' in chunk_opts:
                            if 'jupyter' in meta:
                                meta['jupyter']['output_hidden'] = True
                            else:
                                meta["jupyter"] = {"output_hidden": True}
            else:
                if re_code_inline.search(l):
                    if not meta.get('kernel', '') and any(
                            c.strip() for c in celldata):
                        # if there is markdown text before it, see if there are entire paragraphs
                        # and put in regular markdown cell
                        last_empty_line = len(celldata) - 1
                        while last_empty_line > 0:
                            if celldata[last_empty_line].strip():
                                last_empty_line -= 1
                            else:
                                break
                        if last_empty_line > 0:
                            add_cell(
                                cells,
                                celldata[:last_empty_line + 1],
                                'markdown',
                                metainfo=meta)
                            celldata = celldata[last_empty_line + 1:]
                    # inline markdown ...
                    has_inline_markdown = True
                    # we use hidden to indicate that the input of this code
                    # is supposed to be hidden
                    meta['kernel'] = 'Markdown'
                    meta["jupyter"] = {"source_hidden": True}
                # cell.source in ipynb does not include implicit newlines
                celldata.append(l.rstrip() + "\n")
        else:  # CODE
            if re_code_end.match(l):
                state = MD
                # unconditionally add code blocks regardless of content
                add_cell(cells, celldata, 'code', metainfo=meta)
                celldata = []
                meta = {}
            else:
                if len(celldata) > 0:
                    celldata[-1] = celldata[-1] + "\n"
                celldata.append(l.rstrip())

    if state == CODE and any([c.strip() for c in celldata]):
        add_cell(cells, celldata, 'code', metainfo=meta)
    elif any([c.strip() for c in celldata]):
        add_cell(cells, celldata, 'markdown', metainfo=meta)
    #
    # create header
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
            'kernels': [['SoS', 'sos', '', ''], ['R', 'ir', '', '']]
        }
    }
    if has_inline_markdown:
        metadata['sos']['kernels'].append(['Markdown', 'markdown', '', ''])
    if Rmd_header:
        metadata['Rmd_chunk_options'] = Rmd_header

    nb = new_notebook(cells=cells, metadata=metadata)

    if not output_file:
        nbformat.write(nb, sys.stdout, 4)
    else:
        with open(output_file, 'w') as new_nb:
            nbformat.write(nb, new_nb, 4)
        env.logger.info(f'Jupyter notebook saved to {output_file}')
