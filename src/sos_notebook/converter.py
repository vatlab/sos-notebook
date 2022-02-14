#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import argparse
import os
import sys
import tempfile
import time
from io import StringIO

import nbformat
import pkg_resources
import sos
from nbconvert.exporters import Exporter
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook
from sos.syntax import SOS_SECTION_HEADER
from sos.utils import env


def execute_sos_notebook(input_notebook,
                         output_notebook=None,
                         return_content=True,
                         parameters={}):
    # execute input notebook
    # if input_notebook is a string, it will be loaded. Otherwise it should be a notebook object
    # if output_notebook is a string, it will be used as output filename. Otherwise
    # the notebook will be returned.
    try:
        from papermill.execute import execute_notebook
    except ImportError:
        raise RuntimeError(
            'Please install papermill for the use of option --execute.')

    if not any(entrypoint.name == 'sos'
               for entrypoint in pkg_resources.iter_entry_points(
                   group='papermill.engine')):
        raise RuntimeError(
            'Please install sos-papermill for the use of option --execute.')

    if isinstance(input_notebook, str):
        input_file = input_notebook
    else:
        input_file = tempfile.NamedTemporaryFile(
            prefix='__tmp_input_nb',
            dir=os.getcwd(),
            suffix='.ipynb',
            delete=False).name
        with open(input_file, 'w') as notebook_file:
            nbformat.write(input_notebook, notebook_file, 4)

    if output_notebook is None:
        output_file = tempfile.NamedTemporaryFile(
            prefix='__tmp_output_nb',
            dir=os.getcwd(),
            suffix='.ipynb',
            delete=False).name
    else:
        output_file = output_notebook

    execute_notebook(
        input_path=input_file,
        output_path=output_file,
        engine_name='sos',
        kernel_name='sos',
        parameters=parameters)

    if os.path.basename(input_file).startswith('__tmp_input_nb'):
        try:
            os.remove(input_file)
        except Exception as e:
            env.logger.warning(
                f'Failed to remove temporary input file {input_file}: {e}')

    if os.path.basename(output_file).startswith(
            '__tmp_output_nb') and return_content:
        new_nb = nbformat.read(output_file, nbformat.NO_CONVERT)
        try:
            os.remove(output_file)
        except Exception as e:
            env.logger.warning(
                f'Failed to remove temporary output file {output_file}: {e}')
        return new_nb
    else:
        return output_file


# This class cannot be defined in .kernel because it would cause some
# weird problem with unittesting not able to resolve __main__
class SoS_Exporter(Exporter):

    def __init__(self, config=None, **kwargs):
        self.output_extension = '.sos'
        self.output_mimetype = 'text/x-sos'
        Exporter.__init__(self, config, **kwargs)

    def content_from_notebook_cell(self, cell, fh, idx=0):
        # in non-all mode, markdown cells are ignored because they can be mistakenly
        # treated as markdown content of an action or script #806
        if cell.cell_type != "code":
            return
        #
        # Non-sos code cells are also ignored
        fh.write(f'# cell {idx + 1}, kernel={cell.metadata["kernel"]}\n{cell.source}\n\n')
        return idx

    def workflow_from_notebook_cell(self, cell, fh, idx=0):
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
            for idx, cell in enumerate(cells):
                if 'all_content' in kwargs and kwargs['all_content']:
                    self.content_from_notebook_cell(cell, fh, idx)
                else:
                    self.workflow_from_notebook_cell(cell, fh, idx)
            content = fh.getvalue()
        resources['output_extension'] = '.sos'
        return content, resources


#
# Converter to Notebook
#


class ScriptToNotebookConverter():

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'sos convert FILE.sos FILE._ipynb (or --to ipynb)',
            description='''Convert a sos script to Jupyter notebook (.ipynb)
                so that it can be opened by Jupyter notebook.''')
        return parser

    def convert(self, script_file, notebook_file, args=None, unknown_args=None):
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
                            add_cell(cells, content[:i + 1], cell_type,
                                     cell_count, metainfo)
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
# notebook to sos script
#


class NotebookToScriptConverter(object):

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'sos convert FILE.ipynb FILE.sos (or --to sos)',
            description='''Export Jupyter notebook with a SoS kernel to a
            .sos file. The cells are presented in the .sos file as
            cell structure lines, which will be ignored if executed
            in batch mode ''')
        parser.add_argument('-a',
            '--all',
            action='store_true',
            help='''If set, export all cells to the output file, which
                does not have to be a valid sos workflow.''')
        return parser

    def convert(self, notebook_file, sos_file, args=None, unknown_args=None):
        '''
        Convert a ipython notebook to sos format.
        '''
        if unknown_args:
            raise ValueError(f'Unrecognized parameter {unknown_args}')
        exporter = SoS_Exporter()
        notebook = nbformat.read(notebook_file, nbformat.NO_CONVERT)
        output, _ = exporter.from_notebook_node(notebook, {}, all_content=args.all if args else False)
        if not sos_file:
            sys.stdout.write(output)
        elif isinstance(sos_file, str):
            with open(sos_file, 'w') as sos:
                sos.write(output)
            env.logger.info(f'SoS script saved to {sos_file}')
        else:
            sos_file.write(output)


#
# notebook to HTML
#

def get_template_args():
    return ['--TemplateExporter.extra_template_basedirs', os.path.join(f'{os.path.split(os.path.abspath(__file__))[0]}', 'templates')]


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
                    '--output', tmp
                ] + ([] if unknown_args is None else unknown_args),
                stderr=err)
        with open(tmp_stderr) as err:
            err_msg = err.read()
        if ret != 0:
            env.logger.error(err_msg)
            raise RuntimeError(
                f'Failed to convert {notebook_file} to {to_format} format')
        else:
            # identify output files
            dest_file = err_msg.rsplit()[-1]
            if not os.path.isfile(dest_file):
                env.logger.error(err_msg)
                raise RuntimeError('Failed to get converted file.')
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
            os.path.abspath(output_file)
        ] + ([] if unknown_args is None else unknown_args))
        if ret != 0:
            raise RuntimeError(
                f'Failed to convert {notebook_file} to {to_format} format')
        else:
            env.logger.info(f'Output saved to {output_file}')

def _is_int(value):
    """Use casting to check if value can convert to an `int`."""
    try:
        int(value)
    except ValueError:
        return False
    else:
        return True


def _is_float(value):
    """Use casting to check if value can convert to a `float`."""
    try:
        float(value)
    except ValueError:
        return False
    else:
        return True

def parse_papermill_parameters(values):
    parameters = {}
    for value in values:
        if '=' not in value:
            parameters[value] = True
            contineu
        k, v = value.split('=', 1)
        if v == "True":
            parameters[k] = True
        elif v == "False":
            parameters[k] = False
        elif value == "None":
            parameters[k] = None
        elif _is_int(v):
            parameters[k] = int(v)
        elif _is_float(v):
            parameters[k] = float(v)
        else:
            parameters[k] = v
    return parameters


class NotebookToHTMLConverter(object):

    def get_parser(self):
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
            nargs='*',
            help='''Execute the workflow using sos-papermill before exporting to HTML format.
                One or more parameters are acceptable and should be specified as name=value,
                where the type of value will be automatically guessed. An exception of this
                rule is that `name' without `=` will be considered as value True.'''
        )
        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            help='''If specified, save content of all cells to .sos file.'''
        )
        parser.add_argument(
            '-v',
            '--view',
            action='store_true',
            help='''Open the output file in a broswer. In case no html file is specified,
            this option will display the HTML file in a browser, instead of writing its
            content to standard output.''')
        return parser

    def convert(self,
                notebook_file,
                output_file,
                sargs=None,
                unknown_args=None):
        from nbconvert.exporters.html import HTMLExporter
        if unknown_args is None:
            unknown_args = []
        if sargs.template:
            template_path, template_name = os.path.split(sargs.template)
            if template_path == '':
                unknown_args = get_template_args() + ['--template', template_name] + unknown_args
            else:
                unknown_args = get_template_args() + \
                    ['--TemplateExporter.extra_template_basedirs', template_path,
                     '--template', template_name] + unknown_args

        if sargs.execute is not None:
            notebook_file = execute_sos_notebook(
                notebook_file, return_content=False,
                parameters=parse_papermill_parameters(sargs.execute))

        export_notebook(
            HTMLExporter,
            'html',
            notebook_file,
            output_file,
            unknown_args,
            view=sargs.view)

        if os.path.basename(notebook_file).startswith('__tmp_output_nb'):
            try:
                os.remove(notebook_file)
            except Exception as e:
                env.logger.warning(
                    f'Failed to remove temporary output file {noteput_file}: {e}'
                )


#
# Notebook to PDF
#


class NotebookToPDFConverter(object):

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'sos convert FILE.ipynb FILE.pdf (or --to pdf)',
            description='''Export Jupyter notebook with a SoS kernel to a
            .pdf file. Additional command line arguments are passed directly to
            command "jupyter nbconvert --to pdf" so please refer to nbconvert manual for
            available options.''')
        parser.add_argument(
            '-e',
            '--execute',
            nargs='*',
            help='''Execute the workflow using sos-papermill before exporting to PDF format.
                One or more parameters are acceptable and should be specified as name=value,
                where the type of value will be automatically guessed. An exception of this
                rule is that `name' without `=` will be considered as value True.'''
        )
        parser.add_argument(
            '--template',
            help='''Template to export Jupyter notebook with sos kernel. SoS provides a number
            of templates, with sos-report displays markdown cells and only output of cells with
            prominent tag, and a control panel to control the display of the rest of the content
            ''')
        return parser

    def convert(self,
                notebook_file,
                output_file,
                sargs=None,
                unknown_args=None):
        from nbconvert.exporters.pdf import PDFExporter
        if sargs.execute is not None:
            notebook_file = execute_sos_notebook(
                notebook_file, return_content=False,
                parameters=parse_papermill_parameters(sargs.execute))

        if unknown_args is None:
            unknown_args = []
        if sargs.template:
            template_path, template_name = os.path.split(sargs.template)
            if template_path == '':
                unknown_args = get_template_args() + ['--template', template_name] + unknown_args
            else:
                unknown_args = get_template_args() + \
                    ['--TemplateExporter.extra_template_basedirs', template_path,
                     '--template', template_name] + unknown_args

        # jupyter convert will add extension to output file...
        if output_file is not None and output_file.endswith('.pdf'):
            output_file = output_file[:-4]
        export_notebook(PDFExporter, 'pdf', notebook_file, output_file,
                        get_template_args() + unknown_args)

        if os.path.basename(notebook_file).startswith('__tmp_output_nb'):
            try:
                os.remove(notebook_file)
            except Exception as e:
                env.logger.warning(
                    f'Failed to remove temporary output file {notebook_file}: {e}'
                )
#
# Notebook to Markdown
#


class NotebookToMarkdownConverter(object):

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'sos convert FILE.ipynb FILE.md (or --to md)',
            description='''Export Jupyter notebook with a SoS kernel to a
            markdown file. Additional command line arguments are passed directly to
            command "jupyter nbconvert --to markdown" so please refer to nbconvert manual for
            available options.''')
        parser.add_argument(
            '-e',
            '--execute',
            nargs='*',
            help='''Execute the workflow using sos-papermill before exporting to markdown format.
                One or more parameters are acceptable and should be specified as name=value,
                where the type of value will be automatically guessed. An exception of this
                rule is that `name' without `=` will be considered as value True.'''
        )
        return parser

    def convert(self,
                notebook_file,
                output_file,
                sargs=None,
                unknown_args=None):
        from nbconvert.exporters.markdown import MarkdownExporter
        if sargs.execute is not None:
            notebook_file = execute_sos_notebook(
                notebook_file, return_content=False,
                parameters=parse_papermill_parameters(sargs.execute))

        export_notebook(
            MarkdownExporter, 'markdown', notebook_file, output_file,
            get_template_args() + ['--template', 'sos-markdown'] + unknown_args)

        if os.path.basename(notebook_file).startswith('__tmp_output_nb'):
            try:
                os.remove(notebook_file)
            except Exception as e:
                env.logger.warning(
                    f'Failed to remove temporary output file {notebook_file}: {e}'
                )
#
# Notebook to Notebook
#


class NotebookToNotebookConverter(object):

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'sos convert FILE.ipynb FILE.ipynb (or --to ipynb)',
            description='''Export a Jupyter notebook with a non-SoS kernel to a SoS notebook
            with SoS kernel, or from a SoS notebook to a regular notebook with specified kernel,
            or execute a SoS notebook.''')
        parser.add_argument(
            '-k',
            '--kernel',
            help='''Kernel for the destination notebook. The default kernel is
            SoS which converts a non-SoS notebook to SoS Notebook. If another kernel is specified,
            this command will remove cell-specific kernel information and convert a SoS Notebook
            to regular notebook with specified kernel.''')
        parser.add_argument(
            '--python3-to-sos',
            action='store_true',
            help='''Convert python3 cells to SoS.''')
        parser.add_argument(
            '--execute',
            nargs='*',
            help='''Execute the workflow using sos-papermill. One or more parameters
                 are acceptable and should be specified as name=value,
                where the type of value will be automatically guessed. An exception of this
                rule is that `name' without `=` will be considered as value True.'''
        )
        parser.add_argument(
            '--inplace',
            action='store_true',
            help='''Overwrite input notebook with the output.''')
        return parser

    def nonSoS_to_SoS_notebook(self, notebook, args):
        '''Converting a nonSoS notebook to SoS notebook by adding kernel metadata'''
        # get the kernel of the notebook
        # this is like 'R', there is another 'display_name'
        lan_name = notebook['metadata']['kernelspec']['language']
        if lan_name == 'python':
            lan_name = 'Python3'
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
        kernels = [['SoS', 'sos', '', '', '']]
        if to_lan != 'SoS':
            kernels += [[to_lan, to_kernel, '', '', '']]
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
                'kernels': kernels
            }
        }
        return new_notebook(cells=cells, metadata=metadata)

    def SoS_to_nonSoS_notebook(self, notebook, args):
        kernel_name = notebook['metadata']['kernelspec']['name']

        if kernel_name != 'sos':
            raise ValueError(
                f'Cannot convert a notebook with kernel {kernel_name} to a notebook with kernel {args.kernel}'
            )

        all_subkernels = [
            x[1]
            for x in notebook['metadata']['sos']['kernels']
            if x[1] != 'sos'
        ]
        kinfo = [
            x for x in notebook['metadata']['sos']['kernels']
            if x[1] == args.kernel
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

    def convert(self,
                notebook_file,
                output_file,
                sargs=None,
                unknown_args=None):
        notebook = nbformat.read(notebook_file, nbformat.NO_CONVERT)
        kernel_name = notebook['metadata']['kernelspec']['name']

        nb = None
        # what are we supposed to do?
        if kernel_name == 'sos' and sargs.kernel and sargs.kernel not in (
                'sos', 'SoS'):
            # sos => nonSoS
            if sargs.execute is not None:
                notebook = execute_sos_notebook(
                    notebook_file,
                    parameters=parse_papermill_parameters(sargs.execute))
            nb = self.SoS_to_nonSoS_notebook(notebook, sargs)
        elif kernel_name == 'sos' and not sargs.kernel:
            if sargs.execute is not None:
                if output_file and notebook_file != output_file:
                    execute_sos_notebook(
                        notebook_file,
                        output_file,
                        parameters=parse_papermill_parameters(sargs.execute))
                    env.logger.info(f'Jupyter notebook saved to {output_file}')
                    return
                else:
                    nb = execute_sos_notebook(
                        notebook_file,
                        parameters=parse_papermill_parameters(sargs.execute))
            # sos => sos
        elif kernel_name != 'sos' and sargs.kernel in ('sos', 'SoS', None):
            nb = self.nonSoS_to_SoS_notebook(notebook, sargs)
            if sargs.execute is not None:
                nb = execute_sos_notebook(
                    nb, parameters=parse_papermill_parameters(sargs.execute))

        if nb is None:
            # nothing to do (e.g. sos -> sos) without --execute
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
