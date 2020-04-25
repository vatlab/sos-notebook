import argparse
import copy
import fnmatch
import os
import pydoc
import re
import shlex
import builtins
import subprocess
import sys
from collections import Sized, OrderedDict, Sequence
from io import StringIO
from types import ModuleType

import pandas as pd
from IPython.core.error import UsageError
from IPython.lib.clipboard import (ClipboardEmpty, osx_clipboard_get,
                                   tkinter_clipboard_get)
from jupyter_client import find_connection_file
from sos.eval import interpolate
from sos.syntax import SOS_SECTION_HEADER
from sos.utils import env, pretty_size, short_repr, pexpect_run, load_config_files
from sos._version import __version__


class SoS_Magic(object):
    name = 'BaseMagic'

    def __init__(self, kernel):
        self.sos_kernel = kernel
        self.pattern = re.compile(fr'%{self.name}(\s|$)')

    def _interpolate_text(self, text, quiet=False):
        # interpolate command
        try:
            new_text = interpolate(text, local_dict=env.sos_dict._dict)
            if new_text != text and not quiet:
                self.sos_kernel.send_response(
                    self.sos_kernel.iopub_socket, 'display_data', {
                        'metadata': {},
                        'data': {
                            'text/html':
                                f'<div class="sos_hint">> {new_text.strip() + "<br>"}</div>'
                        }
                    })
            return new_text
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to interpolate {short_repr(text)}: {e}\n')
            return None

    def get_magic_and_code(self, code, warn_remaining=False):
        if code.startswith('%') or code.startswith('!'):
            lines = re.split(r'(?<!\\)\n', code, 1)
            # remove lines joint by \
            lines[0] = lines[0].replace('\\\n', '')
        else:
            lines = code.split('\n', 1)

        pieces = self._interpolate_text(
            lines[0], quiet=False).strip().split(None, 1)
        if len(pieces) == 2:
            command_line = pieces[1]
        else:
            command_line = ''
        remaining_code = lines[1] if len(lines) > 1 else ''
        if warn_remaining and remaining_code.strip():
            self.sos_kernel.warn('Statement {} ignored'.format(
                short_repr(remaining_code)))
        return command_line, remaining_code

    def match(self, code):
        return self.pattern.match(code)

    def run_shell_command(self, cmd):
        # interpolate command
        if not cmd:
            return
        try:
            with self.sos_kernel.redirect_sos_io():
                pexpect_run(
                    cmd,
                    shell=True,
                    win_width=40
                    if self.sos_kernel._meta['cell_id'] == "" else 80)
        except Exception as e:
            self.sos_kernel.warn(e)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        raise RuntimeError(f'Unimplemented magic {self.name}')

    def _parse_error(self, msg):
        self.sos_kernel.warn(msg)


class Command_Magic(SoS_Magic):
    name = '!'

    def match(self, code):
        return code.startswith('!')

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        self.run_shell_command(code.split(' ')[0][1:] + ' ' + options)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Capture_Magic(SoS_Magic):
    name = 'capture'

    def __init__(self, kernel):
        super(Capture_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%capture',
            description='''Capture output from a subkernel as variable in SoS'''
        )
        parser.add_argument(
            'msg_type',
            nargs='?',
            default='raw',
            choices=[
                'stdout', 'stderr', 'text', 'markdown', 'html', 'raw', 'error'
            ],
            help='''Message type to capture. In terms of Jupyter message types,
                "stdout" refers to "stream" message with "stdout" type, "stderr"
                refers to "stream" message with "stderr" type, "text", "markdown"
                and "html" refers to "display_data" or "execute_result" messages
                with "text/plain", "text/markdown" and "text/html" type respectively,
                and 'error' refers to "evalue" of "error" messages.
                If no value or "raw" is specified, all returned messages will be
                returned in alist format, and will be displayed in the console panel.
                This will help you determine the right type to capture.''')
        parser.add_argument(
            '--as',
            dest='as_type',
            default='text',
            nargs='?',
            choices=('text', 'json', 'csv', 'tsv'),
            help='''How to interpret the captured text. This only applicable to stdout, stderr and
                text message type where the text from cell output will be collected. If this
                option is given, SoS will try to parse the text as json, csv (comma separated text),
                tsv (tab separated text), and store text (from text), Pandas DataFrame
                (from csv or tsv), dict or other types (from json) to the variable.'''
        )
        grp = parser.add_mutually_exclusive_group(required=False)
        grp.add_argument(
            '-t',
            '--to',
            dest='__to__',
            metavar='VAR',
            help='''Name of variable to which the captured content will be saved. If no varialbe is
                specified, the return value will be saved to variable "__captured" and be displayed
                at the side panel. ''')
        grp.add_argument(
            '-a',
            '--append',
            dest='__append__',
            metavar='VAR',
            help='''Name of variable to which the captured content will be appended.
                            This option is equivalent to --to if VAR does not exist. If VAR exists
                            and is of the same type of new content (str or dict or DataFrame), the
                            new content will be appended to VAR if VAR is of str (str concatenation),
                            dict (dict update), or DataFrame (DataFrame.append) types. If VAR is of
                            list type, the new content will be appended to the end of the list.'''
        )
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        try:
            self.sos_kernel._meta['capture_result'] = []
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        finally:
            # parse capture_result
            content = ''
            if args.msg_type == 'stdout':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'stream' and msg[1]['name'] == 'stdout':
                        content += msg[1]['text']
            elif args.msg_type == 'stderr':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'stream' and msg[1]['name'] == 'stderr':
                        content += msg[1]['text']
            elif args.msg_type == 'text':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[
                            1] and 'text/plain' in msg[1]['data']:
                        content += msg[1]['data']['text/plain']
            elif args.msg_type == 'markdown':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[
                            1] and 'text/markdown' in msg[1]['data']:
                        content += msg[1]['data']['text/markdown']
            elif args.msg_type == 'html':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[
                            1] and 'text/html' in msg[1]['data']:
                        content += msg[1]['data']['text/html']
            elif args.msg_type == 'error':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'error' and 'evalue' in msg[1]:
                        content += msg[1]['evalue']
            else:
                args.as_type = 'raw'
                content = self.sos_kernel._meta['capture_result']

            env.log_to_file(
                'MAGIC',
                f'Captured {self.sos_kernel._meta["capture_result"][:40]}')
            if not args.as_type or args.as_type == 'text':
                if not isinstance(content, str):
                    self.sos_kernel.warn(
                        'Option --as is only available for message types stdout, stderr, and text.'
                    )
            elif args.as_type == 'json':
                import json
                try:
                    if isinstance(content, str):
                        content = json.loads(content)
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.'
                        )
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in JSON format, text returned: {e}'
                    )
            elif args.as_type == 'csv':
                try:
                    if isinstance(content, str):
                        with StringIO(content) as ifile:
                            content = pd.read_csv(ifile)
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.'
                        )
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in {args.as_type} format, text returned: {e}'
                    )
            elif args.as_type == 'tsv':
                try:
                    if isinstance(content, str):
                        with StringIO(content) as ifile:
                            content = pd.read_csv(ifile, sep='\t')
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.'
                        )
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in {args.as_type} format, text returned: {e}'
                    )
            #
            if args.__to__ and not args.__to__.isidentifier():
                self.sos_kernel.warn(f'Invalid variable name {args.__to__}')
                self.sos_kernel._meta['capture_result'] = None
                return
            if args.__append__ and not args.__append__.isidentifier():
                self.sos_kernel.warn(f'Invalid variable name {args.__append__}')
                self.sos_kernel._meta['capture_result'] = None
                return

            if args.__to__:
                env.sos_dict.set(args.__to__, content)
            elif args.__append__:
                if args.__append__ not in env.sos_dict:
                    env.sos_dict.set(args.__append__, content)
                elif isinstance(env.sos_dict[args.__append__], str):
                    if isinstance(content, str):
                        env.sos_dict[args.__append__] += content
                    else:
                        self.sos_kernel.warn(
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}'
                        )
                elif isinstance(env.sos_dict[args.__append__], dict):
                    if isinstance(content, dict):
                        env.sos_dict[args.__append__].update(content)
                    else:
                        self.sos_kernel.warn(
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}'
                        )
                elif isinstance(env.sos_dict[args.__append__], pd.DataFrame):
                    if isinstance(content, pd.DataFrame):
                        env.sos_dict.set(
                            args.__append__,
                            env.sos_dict[args.__append__].append(content))
                    else:
                        self.sos_kernel.warn(
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}'
                        )
                elif isinstance(env.sos_dict[args.__append__], list):
                    env.sos_dict[args.__append__].append(content)
                else:
                    self.sos_kernel.warn(
                        f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}'
                    )
            else:
                env.sos_dict.set('__captured', content)
                import pprint
                self.sos_kernel.send_frontend_msg(
                    'display_data', {
                        'metadata': {},
                        'data': {
                            'text/html':
                                f'<div class="sos_hint">Cell output captured to variable __captured with content</div>'
                        }
                    })
                self.sos_kernel.send_frontend_msg('display_data', {
                    'metadata': {},
                    'data': {
                        'text/plain': pprint.pformat(content)
                    }
                })
        self.sos_kernel._meta['capture_result'] = None


class Cd_Magic(SoS_Magic):
    name = 'cd'

    def __init__(self, kernel):
        super(Cd_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%cd',
            description='''change directory of SoS and all subkernels.''')
        parser.add_argument('dir', help='''destination directory''')
        parser.error = self._parse_error
        return parser

    def handle_magic_cd(self, option):
        if not option:
            return
        to_dir = option.strip()
        try:
            os.chdir(os.path.expanduser(to_dir))
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                          'stream', {
                                              'name': 'stdout',
                                              'text': os.getcwd()
                                          })
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to change dir to {os.path.expanduser(to_dir)}: {e}')
            return
        #
        cur_kernel = self.sos_kernel.kernel
        try:
            for kernel in self.sos_kernel.kernels.keys():
                if kernel not in self.sos_kernel.supported_languages:
                    self.sos_kernel.warn(
                        f'Current directory of kernel {kernel} is not changed: unsupported language'
                    )
                    continue
                lan = self.sos_kernel.supported_languages[kernel]
                if hasattr(lan, 'cd_command'):
                    try:
                        self.sos_kernel.switch_kernel(kernel)
                        cmd = interpolate(lan.cd_command, {'dir': to_dir})
                        self.sos_kernel.run_cell(
                            cmd,
                            True,
                            False,
                            on_error=f'Failed to execute {cmd} in {kernel}')
                    except Exception as e:
                        self.sos_kernel.warn(
                            f'Current directory of kernel {kernel} is not changed: {e}'
                        )
                else:
                    self.sos_kernel.warn(
                        f'Current directory of kernel {kernel} is not changed: cd_command not defined'
                    )
        finally:
            self.sos_kernel.switch_kernel(cur_kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        self.handle_magic_cd(args.dir)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Clear_Magic(SoS_Magic):
    name = 'clear'

    def __init__(self, kernel):
        super(Clear_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        self.sos_kernel.warn('Magic %clear is deprecated.')
        options, remaining_code = self.get_magic_and_code(code, False)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class ConnectInfo_Magic(SoS_Magic):
    name = 'connectinfo'

    def __init__(self, kernel):
        super(ConnectInfo_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        cfile = find_connection_file()
        with open(cfile) as conn:
            conn_info = conn.read()
        self.sos_kernel.send_response(
            self.sos_kernel.iopub_socket, 'stream', {
                'name': 'stdout',
                'text': 'Connection file: {}\n{}'.format(cfile, conn_info)
            })
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Convert_Magic(SoS_Magic):
    name = 'convert'

    def __init__(self, kernel):
        super(Convert_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%convert',
            description='''Convert the current notebook to another format.''')
        parser.add_argument(
            'filename',
            nargs='?',
            help='''Filename of saved report or script. Default to notebookname with file
            extension determined by option --to.''')
        parser.add_argument(
            '-t',
            '--to',
            dest='__to__',
            choices=['sos', 'html'],
            help='''Destination format, default to html.''')
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help='''If destination file already exists, overwrite it.''')
        parser.add_argument(
            '--template',
            default='default-sos-template',
            help='''Template to generate HTML output. The default template is a
            template defined by configuration key default-sos-template, or
            sos-report-toc if such a key does not exist.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        # get the saved filename
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
            if args.filename:
                filename = args.filename
                if filename.lower().endswith('.html'):
                    if args.__to__ is None:
                        ftype = 'html'
                    elif args.__to__ != 'html':
                        self.sos_kernel.warn(
                            f'%sossave to an .html file in {args.__to__} format'
                        )
                        ftype = args.__to__
                else:
                    ftype = 'sos'
            else:
                ftype = args.__to__ if args.__to__ else 'sos'
                filename = self.sos_kernel._meta['notebook_name'] + '.' + ftype

            filename = os.path.expanduser(filename)

            if os.path.isfile(filename) and not args.force:
                raise ValueError(
                    f'Cannot overwrite existing output file {filename}')
            # self.sos_kernel.send_frontend_msg('preview-workflow', self.sos_kernel._meta['workflow'])
            if ftype == 'sos':
                with open(filename, 'w') as script:
                    script.write(self.sos_kernel._meta['workflow'])
            else:
                # convert to sos report
                from .converter import NotebookToHTMLConverter
                arg = argparse.Namespace()
                if args.template == 'default-sos-template':
                    cfg = load_config_files()
                    if 'default-sos-template' in cfg:
                        arg.template = cfg['default-sos-template']
                    else:
                        arg.template = 'sos-report-toc'
                else:
                    arg.template = args.template
                arg.view = False
                arg.execute = False
                NotebookToHTMLConverter().convert(
                    self.sos_kernel._meta['notebook_name'] + '.ipynb',
                    filename,
                    sargs=arg,
                    unknown_args=[])

            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/plain':
                            f'Notebook saved to {filename}\n',
                        'text/html':
                            f'<div class="sos_hint">Notebook saved to <a href="{filename}" target="_blank">{filename}</a></div>'
                    }
                })
            #
            return
        except Exception as e:
            msg = {
                'status': 'error',
                'ename': e.__class__.__name__,
                'evalue': str(e),
                'traceback': [],
                'execution_count': self.sos_kernel._execution_count,
            }
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'error',
                                          msg)
            return msg


class Debug_Magic(SoS_Magic):
    name = 'debug'

    def __init__(self, kernel):
        super(Debug_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        self.sos_kernel.warn(
            'Magic %debug is deprecated. Please set environment variable SOS_DEBUG to ALL or a comma '
            'separated topics such as KERNEL, MESSAGE, and MAGIC, and check log messages in ~/.sos/sos_debug.log.'
        )
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Dict_Magic(SoS_Magic):
    name = 'dict'

    def __init__(self, kernel):
        super(Dict_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%dict', description='Inspect or reset SoS dictionary')
        parser.add_argument('vars', nargs='*')
        parser.add_argument(
            '-k', '--keys', action='store_true', help='Return only keys')
        parser.add_argument(
            '-r',
            '--reset',
            action='store_true',
            help='Rest SoS dictionary (clear all user variables)')
        parser.add_argument(
            '-a',
            '--all',
            action='store_true',
            help='Return all variales, including system functions and variables'
        )
        parser.add_argument(
            '-d',
            '--del',
            nargs='+',
            metavar='VAR',
            dest='__del__',
            help='Remove specified variables from SoS dictionary')
        parser.error = self._parse_error
        return parser

    def handle_magic_dict(self, line):
        'Magic that displays content of the dictionary'
        # do not return __builtins__ beacuse it is too long...
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(line))
        except SystemExit:
            return

        for x in args.vars:
            if x not in env.sos_dict:
                self.sos_kernel.warn(
                    'Unrecognized sosdict option or variable name {}'.format(x))
                return

        if args.reset:
            from sos.executor_utils import prepare_env
            prepare_env('')
            return

        if args.__del__:
            for x in args.__del__:
                if x in env.sos_dict:
                    env.sos_dict.pop(x)
            return

        if args.keys:
            if args.all:
                self.sos_kernel.send_result(env.sos_dict._dict.keys())
            elif args.vars:
                self.sos_kernel.send_result(set(args.vars))
            else:
                self.sos_kernel.send_result({
                    x for x in env.sos_dict._dict.keys()
                    if not x.startswith('__')
                } - self.sos_kernel.original_keys)
        else:
            if args.all:
                self.sos_kernel.send_result(env.sos_dict._dict)
            elif args.vars:
                self.sos_kernel.send_result({
                    x: y
                    for x, y in env.sos_dict._dict.items()
                    if x in args.vars
                })
            else:
                self.sos_kernel.send_result({
                    x: y
                    for x, y in env.sos_dict._dict.items()
                    if x not in self.sos_kernel.original_keys and
                    not x.startswith('__')
                })

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        # %dict should be the last magic
        options, remaining_code = self.get_magic_and_code(code, False)
        self.handle_magic_dict(options)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Env_Magic(SoS_Magic):
    name = 'env'

    def __init__(self, kernel):
        super(Env_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%env',
            description='''Adjust the running environment for the cell, such as running
                with a new dict, under a different directory, and expect an error from the
                execution of the cell.''')
        parser.add_argument(
            '--new',
            action='store_true',
            help='''Execute workflow with a fresh SoS environment''')
        parser.add_argument(
            '--set',
            nargs='+',
            help='''Set one more more environment variables. Parameters of this
                option can be 'KEY=VALUE' or just 'KEY'. An empty evnironment
                variable will be set in the latter case. Note that the environments
                will be reset out of the cell.''')
        parser.add_argument(
            '--prepend-path',
            nargs='+',
            help='''Prepend one or more paths before "$PATH" so that commands
                in those paths will take priority. Note that `$PATH` will be reset
                after the completion of the cell.''')
        parser.add_argument(
            '--tempdir',
            action='store_true',
            help='''Execute workflow in temporary directory, which will be removed
                after the completion of the cell. Therefore you cannot use this option
                when running the cell content in background mode.''')
        parser.add_argument(
            '--expect-error',
            action='store_true',
            help='''If set, expect error from the excution and report
                success if an error occurs, and report error if an error
                does not occur.''')
        parser.add_argument(
            '--allow-error',
            action='store_true',
            help='''If set, return success even if the underlying cell reports
                error.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        import tempfile
        import shutil
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        try:
            old_dict = env.sos_dict
            new_dir = None
            original_env = None
            if args.new:
                from sos.utils import WorkflowDict
                from sos.eval import SoS_exec
                env.sos_dict = WorkflowDict()
                SoS_exec('from sos.runtime import *', None)
                env.sos_dict.set('__interactive__', True)
                env.sos_dict.set('CONFIG', old_dict['CONFIG'])

            old_dir = os.getcwd()
            if args.tempdir:
                new_dir = tempfile.mkdtemp()
                env.exec_dir = os.path.abspath(new_dir)
                os.chdir(new_dir)

            if args.set or args.prepend_path:
                original_env = copy.deepcopy(os.environ)

            if args.set:
                for item in args.set:
                    if '=' in item:
                        key, value = item.split('=', 1)
                    else:
                        key = item
                        value = ''
                    os.environ[key] = value

            if args.prepend_path:
                new_path = os.pathsep.join(args.prepend_path)
                if new_path:
                    os.environ['PATH'] = os.pathsep.join(
                        [new_path, os.environ.get('PATH', '')])

            if args.expect_error or args.allow_error:
                self.sos_kernel._meta['suppress_error'] = True
            ret = self.sos_kernel._do_execute(remaining_code, silent,
                                              store_history, user_expressions,
                                              allow_stdin)
            if args.expect_error:
                if ret['status'] == 'error':
                    # self.sos_kernel.warn('\nSandbox execution failed.')
                    return {
                        'status': 'ok',
                        'payload': [],
                        'user_expressions': {},
                        'execution_count': self.sos_kernel._execution_count
                    }
                else:
                    return self.sos_kernel.notify_error(
                        RuntimeError(
                            'No error received with option --expect error.'))
            elif args.allow_error:
                return {
                    'status': 'ok',
                    'payload': [],
                    'user_expressions': {},
                    'execution_count': self.sos_kernel._execution_count
                }
            else:
                return ret
        finally:
            env.sos_dict = old_dict
            if new_dir is not None:
                os.chdir(old_dir)
                shutil.rmtree(new_dir)
            if original_env is not None:
                os.environ.clear()
                os.environ.update(original_env)
            self.sos_kernel._meta['suppress_error'] = False


class Expand_Magic(SoS_Magic):
    name = 'expand'

    def __init__(self, kernel):
        super(Expand_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%expand',
            description='''Expand the script in the current cell with default ({}) or
                specified sigil.''')
        parser.add_argument(
            'sigil',
            nargs='?',
            help='''Sigil to be used to interpolated the
            texts. It can be quoted, or be specified as two options.''')
        parser.add_argument(
            'right_sigil',
            nargs='?',
            help='''Right sigil if the sigil is
            specified as two pieces.''')
        parser.add_argument(
            '-i',
            '--in',
            dest='kernel',
            help='''Expand the cell content in specific kernel, default to "SoS". This requires
                that the language module supports the "expand" featire.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        lines = code.splitlines()
        options = lines[0]
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options)[1:])
        except SystemExit:
            return
        if self.sos_kernel.kernel.lower() == 'sos':
            self.sos_kernel.warn(
                'Use of %expand magic in SoS cells is deprecated.')
        if args.sigil in ('None', None):
            args.sigil = '{ }'
        if args.right_sigil is not None:
            args.sigil = f'{args.sigil} {args.right_sigil}'
        # now we need to expand the text, but separate the SoS magics first
        lines = lines[1:]
        start_line: int = 0
        for idx, line in enumerate(lines):
            if line.strip() and not any(
                    line.startswith(f'%{x} ')
                    for x in SoS_Magics.names) and not line.startswith('!'):
                start_line = idx
                break
        text = '\n'.join(lines[start_line:])
        try:
            expanded = self.sos_kernel.expand_text_in(
                text, args.sigil, kernel=args.kernel)
            remaining_code = '\n'.join(lines[:start_line] + [expanded]) + '\n'
            # self.sos_kernel.options will be set to inflence the execution of remaing_code
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(e)
            return


class Get_Magic(SoS_Magic):
    name = 'get'

    def __init__(self, kernel):
        super(Get_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%get',
            description='''Get specified variables from another kernel, which is
                by default the SoS kernel.''')
        parser.add_argument(
            '--from',
            dest='__from__',
            help='''Name of kernel from which the variables will be obtained.
                Default to the SoS kernel.''')
        parser.add_argument(
            'vars', nargs='*', help='''Names of SoS variables''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            return self.sos_kernel.notify_error(e)
        self.sos_kernel.get_vars_from(args.vars, args.__from__, explicit=True)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Matplotlib_Magic(SoS_Magic):
    name = 'matplotlib'

    def __init__(self, kernel):
        super(Matplotlib_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%matplotlib', description='''Set matplotlib parser type''')
        parser.add_argument(
            'gui',
            choices=[
                'agg', 'gtk', 'gtk3', 'inline', 'ipympl', 'nbagg', 'notebook',
                'osx', 'pdf', 'ps', 'qt', 'qt4', 'qt5', 'svg', 'tk', 'widget',
                'wx'
            ],
            nargs='?',
            help='''Name of the matplotlib backend to use (‘agg’, ‘gtk’, ‘gtk3’,'''
        )
        parser.add_argument(
            '-l',
            '--list',
            action='store_true',
            help='''Show available matplotlib backends''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        if args.list:
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'stream', {
                    'name':
                        'stdout',
                    'text':
                        'Available matplotlib backends: {}'.format([
                            'agg', 'gtk', 'gtk3', 'inline', 'ipympl', 'nbagg',
                            'notebook', 'osx', 'pdf', 'ps', 'qt', 'qt4', 'qt5',
                            'svg', 'tk', 'widget', 'wx'
                        ])
                })
            return
        try:
            _, backend = self.sos_kernel.shell.enable_matplotlib(args.gui)
            if not args.gui or args.gui == 'auto':
                self.sos_kernel.send_response(
                    self.sos_kernel.iopub_socket, 'stream', {
                        'name': 'stdout',
                        'text': f'Using matplotlib backend {backend}'
                    })
        except Exception as e:
            self.sos_kernel.warn(
                'Failed to set matplotlib backnd {}: {}'.format(options, e))
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Paste_Magic(SoS_Magic):
    name = 'paste'

    def __init__(self, kernel):
        super(Paste_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        if self.sos_kernel._meta.get('batch_mode', False):
            return
        options, remaining_code = self.get_magic_and_code(code, True)
        try:
            self.sos_kernel.options = options
            try:
                if sys.platform == 'darwin':
                    try:
                        code = osx_clipboard_get()
                    except Exception:
                        code = tkinter_clipboard_get()
                else:
                    code = tkinter_clipboard_get()
            except ClipboardEmpty:
                raise UsageError("The clipboard appears to be empty")
            except Exception as e:
                env.logger.warn(f'Failed to get text from the clipboard: {e}')
                return
            #
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'stream', {
                    'name': 'stdout',
                    'text': code.strip() + '\n## -- End pasted text --\n'
                })
            return self.sos_kernel._do_execute(code, silent, store_history,
                                               user_expressions, allow_stdin)
        finally:
            self.sos_kernel.options = ''


class Preview_Magic(SoS_Magic):
    name = 'preview'

    def __init__(self, kernel):
        super(Preview_Magic, self).__init__(kernel)
        self.previewers = None

    def preview_var(self, item, style=None):
        if item in env.sos_dict:
            obj = env.sos_dict[item]
        elif item in dir(builtins):
            obj = getattr(builtins, item)
        else:
            return None, f"Unknown variable {item}"
        # get the basic information of object
        txt = type(obj).__name__
        # we could potentially check the shape of data frame and matrix
        # but then we will need to import the numpy and pandas libraries
        if hasattr(obj, 'shape') and getattr(obj, 'shape') is not None:
            txt += f' of shape {getattr(obj, "shape")}'
        elif isinstance(obj, Sized):
            txt += f' of length {obj.__len__()}'
        if isinstance(obj, ModuleType):
            return txt, ({
                'text/plain': pydoc.render_doc(obj, renderer=pydoc.plaintext)
            }, {})
        elif callable(obj):
            return txt, ({
                'text/plain': pydoc.render_doc(obj, renderer=pydoc.plaintext)
            }, {})
        elif hasattr(obj, 'to_html') and getattr(obj, 'to_html') is not None:
            try:
                from sos.visualize import Visualizer
                result = Visualizer(self.sos_kernel, style).preview(obj)
                if isinstance(result, (list, tuple)) and len(result) == 2:
                    return txt, result
                elif isinstance(result, dict):
                    return txt, (result, {})
                elif result is None:
                    return txt, None
                else:
                    raise ValueError(
                        f'Unrecognized return value from visualizer: {short_repr(result)}.'
                    )
            except Exception as e:
                self.sos_kernel.warn(f'Failed to preview variable: {e}')
                return txt, self.sos_kernel.format_obj(obj)
        else:
            return txt, self.sos_kernel.format_obj(obj)

    def show_preview_result(self, result):
        if not result:
            return
        if isinstance(result, str):
            if result.startswith('HINT: '):
                result = result.splitlines()
                hint_line = result[0][6:].strip()
                result = '\n'.join(result[1:])
                self.sos_kernel.send_frontend_msg(
                    'display_data', {
                        'metadata': {},
                        'data': {
                            'text/html':
                                f'<div class="sos_hint">{hint_line}</div>'
                        }
                    })
            if result:
                self.sos_kernel.send_frontend_msg(
                    'stream',
                    {
                        'name': 'stdout',
                        'text': result
                    },
                )
        elif isinstance(result, dict):
            self.sos_kernel.send_frontend_msg(
                'display_data',
                {
                    'data': result,
                    'metadata': {}
                },
            )
        elif isinstance(result, (list, tuple)) and len(result) == 2:
            self.sos_kernel.send_frontend_msg(
                'display_data',
                {
                    'data': result[0],
                    'metadata': result[1]
                },
            )
        else:
            self.sos_kernel.send_frontend_msg(
                'stream',
                dict(
                    name='stderr',
                    text=f'Unrecognized preview content: {result}'),
            )

    def preview_file(self, filename, style=None):
        if not os.path.isfile(filename):
            self.sos_kernel.warn('\n> ' + filename + ' does not exist')
            return
        self.sos_kernel.send_frontend_msg(
            'display_data', {
                'metadata': {},
                'data': {
                    'text/plain':
                        f'\n> {filename} ({pretty_size(os.path.getsize(filename))}):',
                    'text/html':
                        f'<div class="sos_hint">> {filename} ({pretty_size(os.path.getsize(filename))}):</div>',
                }
            })
        previewer_func = None
        # lazy import of previewers
        if self.previewers is None:
            from sos.preview import get_previewers
            self.previewers = get_previewers()
        for x, y, _ in self.previewers:
            if isinstance(x, str):
                if fnmatch.fnmatch(os.path.basename(filename), x):
                    # we load entrypoint only before it is used. This is to avoid
                    # loading previewers that require additional external modules
                    # we can cache the loaded function but there does not seem to be
                    # a strong performance need for this.
                    previewer_func = y.load()
                    break
            else:
                # it should be a function
                try:
                    if x(filename):
                        try:
                            previewer_func = y.load()
                        except Exception as e:
                            self.sos_kernel.send_frontend_msg(
                                'stream',
                                dict(
                                    name='stderr',
                                    text=f'Failed to load previewer {y}: {e}'),
                            )
                            continue
                        break
                except Exception as e:
                    self.sos_kernel.send_frontend_msg('stream', {
                        'name': 'stderr',
                        'text': str(e)
                    })
                    continue
        #
        # if no previewer can be found
        if previewer_func is None:
            return
        try:
            result = previewer_func(filename, self.sos_kernel, style)
            self.show_preview_result(result)
        except Exception as e:
            env.log_to_file('MAGIC', f'Failed to preview {filename}: {e}')

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%preview',
            description='''Preview files, sos variables, or expressions in the
                side panel, or notebook if side panel is not opened, unless
                options --panel or --notebook is specified.''')
        parser.add_argument(
            'items',
            nargs='*',
            help='''Filename, variable name, or expression. Wildcard characters
                such as '*' and '?' are allowed for filenames.''')
        parser.add_argument(
            '-k',
            '--kernel',
            help='''kernel in which variables will be previewed. By default
            the variable will be previewed in the current kernel of the cell.'''
        )
        parser.add_argument(
            '-w',
            '--workflow',
            action='store_true',
            help='''Preview notebook workflow''')
        # this option is currently hidden
        parser.add_argument(
            '-s',
            '--style',
            choices=['table', 'scatterplot', 'png'],
            help='''Option for preview file or variable, which by default is "table"
            for Pandas DataFrame. The %%preview magic also accepts arbitrary additional
            keyword arguments, which would be interpreted by individual style. Passing
            '-h' with '--style' would display the usage information of particular
            style.''')
        parser.add_argument(
            '-r',
            '--host',
            dest='host',
            metavar='HOST',
            help='''Preview files on specified remote host, which should
            be one of the hosts defined in sos configuration files.''')
        loc = parser.add_mutually_exclusive_group()
        loc.add_argument(
            '-p',
            '--panel',
            action='store_true',
            help='''Preview in side panel even if the panel is currently closed'''
        )
        loc.add_argument(
            '-n',
            '--notebook',
            action='store_true',
            help='''Preview in the main notebook.''')
        parser.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.error = self._parse_error
        return parser

    def handle_magic_preview(self, items, kernel=None, style=None):
        handled = [False for x in items]
        for idx, item in enumerate(items):
            try:
                # quoted
                if (item.startswith('"') and item.endswith('"')) or \
                        (item.startswith("'") and item.endswith("'")):
                    try:
                        item = eval(item)
                    except Exception:
                        pass
                item = os.path.expanduser(item)
                if os.path.isfile(item):
                    self.preview_file(item, style)
                    handled[idx] = True
                    continue
                if os.path.isdir(item):
                    handled[idx] = True
                    _, dirs, files = os.walk(item).__next__()
                    self.sos_kernel.send_frontend_msg(
                        'display_data', {
                            'metadata': {},
                            'data': {
                                'text/plain':
                                    '>>> ' + item + ':\n',
                                'text/html':
                                    f'<div class="sos_hint">> {item}: directory<br>{len(files)}  file{"s" if len(files)>1 else ""}<br>{len(dirs)}  subdirector{"y" if len(dirs)<=1 else "ies"}</div>'
                            }
                        })
                    continue
                else:
                    import glob
                    files = glob.glob(item)
                    if files:
                        for pfile in files:
                            self.preview_file(pfile, style)
                        handled[idx] = True
                        continue
            except Exception as e:
                self.sos_kernel.warn(f'\n> Failed to preview file {item}: {e}')
                continue

        # non-sos kernel
        use_sos = kernel in ('sos', 'SoS') or (kernel is None and
                                               self.sos_kernel.kernel == 'SoS')
        orig_kernel = self.sos_kernel.kernel
        if kernel is not None and self.sos_kernel.kernel != self.sos_kernel.subkernels.find(
                kernel).name:
            self.sos_kernel.switch_kernel(kernel)
        if self.sos_kernel._meta['use_panel']:
            self.sos_kernel.send_frontend_msg('preview-kernel',
                                              self.sos_kernel.kernel)
        try:
            for idx, item in enumerate(items):
                try:
                    # quoted
                    if (item.startswith('"') and item.endswith('"')) or \
                            (item.startswith("'") and item.endswith("'")):
                        try:
                            item = eval(item)
                        except Exception:
                            pass
                    if use_sos:
                        obj_desc, preview = self.preview_var(item, style)
                        if isinstance(preview, str) and preview.startswith(
                                'Unknown variable') and handled[idx]:
                            continue
                        self.sos_kernel.send_frontend_msg(
                            'display_data', {
                                'metadata': {},
                                'data': {
                                    'text/plain':
                                        '>>> ' + item + ':\n',
                                    'text/html':
                                        f'<div class="sos_hint">> {item}: {obj_desc}</div>'
                                }
                            })
                        self.show_preview_result(preview)
                        continue
                    # not sos
                    if self.sos_kernel.kernel in self.sos_kernel.supported_languages:
                        lan = self.sos_kernel.supported_languages[
                            self.sos_kernel.kernel]
                        kinfo = self.sos_kernel.subkernels.find(
                            self.sos_kernel.kernel)
                        lan_obj = lan(self.sos_kernel, kinfo.kernel)
                        if hasattr(lan_obj, 'preview') and callable(
                                lan_obj.preview):
                            try:
                                obj_desc, preview = lan_obj.preview(item)
                                if preview.startswith(
                                        'Unknown variable') and handled[idx]:
                                    continue
                                self.sos_kernel.send_frontend_msg(
                                    'display_data', {
                                        'metadata': {},
                                        'data': {
                                            'text/plain':
                                                '>>> ' + item + ':\n',
                                            'text/html':
                                                f'<div class="sos_hint">> {item}: {obj_desc}</div>'
                                        }
                                    })
                                self.show_preview_result(preview)
                            except Exception:
                                pass
                                # self.sos_kernel.warn(f'Failed to preview {item}: {e}')
                            continue
                    # if no preview function defined
                    # evaluate the expression itself
                    responses = self.sos_kernel.get_response(
                        item,
                        ['stream', 'display_data', 'execute_result', 'error'])
                    if responses:
                        self.sos_kernel.send_frontend_msg(
                            'display_data', {
                                'metadata': {},
                                'data': {
                                    'text/plain':
                                        '>>> ' + item + ':\n',
                                    'text/html':
                                        f'<div class="sos_hint">> {item}:</div>'
                                }
                            })
                        for response in responses:
                            # self.sos_kernel.warn(f'{response[0]} {response[1]}' )
                            if response[0] == 'execute_result':
                                self.sos_kernel.send_frontend_msg(
                                    'display_data', response[1])
                            else:
                                self.sos_kernel.send_frontend_msg(
                                    response[0], response[1])
                    else:
                        raise ValueError(f'Cannot preview expresison {item}')
                except Exception as e:
                    if not handled[idx]:
                        self.sos_kernel.send_frontend_msg(
                            'stream',
                            dict(
                                name='stderr',
                                text='> Failed to preview file or expression {item}'
                            ))
                        env.log_to_file('MAGIC', str(e))
        finally:
            self.sos_kernel.switch_kernel(orig_kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        options = shlex.split(options, posix=False)
        help_option = []
        if ('-s' in options or '--style' in options) and '-h' in options:
            # defer -h to subparser
            options.remove('-h')
            help_option = ['-h']
        try:
            args, style_options = parser.parse_known_args(options)
        except SystemExit:
            return
        #
        style_options.extend(help_option)
        style = {'style': args.style, 'options': style_options}
        #
        if args.panel:
            self.sos_kernel._meta['use_panel'] = True
        elif args.notebook:
            self.sos_kernel._meta['use_panel'] = False
        # else, use default _use_panel
        try:
            # inside a %preview magic, auto preview will be disabled
            self.sos_kernel._no_auto_preview = True
            self.sos_kernel._meta['auto_preview'] = False
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        finally:
            self.sos_kernel._no_auto_preview = False
            # preview workflow
            if args.workflow:
                if self.sos_kernel._meta['batch_mode']:
                    # in batch mode, we cannot use codemirror to format a textarea
                    # and will send the workflow as plain text.
                    # we could send pygments highlighted code to the HTML file, but
                    # adding css is another hassle.
                    self.sos_kernel.send_response(
                        self.sos_kernel.iopub_socket, 'stream', {
                            'name': 'stdout',
                            'text': self.sos_kernel._meta['workflow']
                        })
                else:
                    import random
                    ta_id = 'preview_wf_{}'.format(random.randint(1, 1000000))
                    self.sos_kernel.send_response(
                        self.sos_kernel.iopub_socket, 'display_data', {
                            'data': {
                                'text/plain':
                                    self.sos_kernel._meta['workflow'],
                                'text/html':
                                    f'<textarea id="{ta_id}">{self.sos_kernel._meta["workflow"]}</textarea>'
                            },
                            'metadata': {},
                            'transient': {
                                'display_id': ta_id
                            }
                        })
                    self.sos_kernel.send_frontend_msg(
                        'highlight-workflow',
                        [self.sos_kernel._meta['cell_id'], ta_id])
            if not args.items:
                return
            if args.host is None:
                self.handle_magic_preview(args.items, args.kernel, style)
            elif args.workflow:
                self.sos_kernel.warn('Invalid option --kernel with -r (--host)')
            elif args.kernel:
                self.sos_kernel.warn('Invalid option --kernel with -r (--host)')
            else:
                load_config_files(args.config)
                try:
                    rargs = ['sos', 'preview', '--html'] + options
                    rargs = [
                        x for x in rargs
                        if x not in ('-n', '--notebook', '-p', '--panel')
                    ]
                    env.log_to_file('MAGIC', f'Running "{" ".join(rargs)}"')
                    for msg in eval(subprocess.check_output(rargs)):
                        self.sos_kernel.send_frontend_msg(msg[0], msg[1])
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to preview {args.items} on remote host {args.host}'
                    )
                    env.log_to_file('MAGIC', str(e))


class Pull_Magic(SoS_Magic):
    name = 'pull'

    def __init__(self, kernel):
        super(Pull_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'pull',
            description='''Pull files or directories from remote host to local host'''
        )
        parser.add_argument(
            'items',
            nargs='+',
            help='''Files or directories to be
            retrieved from remote host. The files should be relative to local file
            system. The files to retrieve are determined by "path_map"
            determined by "paths" definitions of local and remote hosts.''')
        parser.add_argument(
            '-f',
            '--from',
            dest='host',
            help='''Remote host to which the files will be sent, which should
            be one of the hosts defined in sos configuration files.''')
        parser.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.add_argument(
            '-v',
            '--verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        parser.error = self._parse_error
        return parser

    def handle_magic_pull(self, args):
        from sos.hosts import Host
        load_config_files(args.config)
        try:
            host = Host(args.host)
            #
            received = host.receive_from_host(args.items)
            #
            msg = '{} item{} received from {}:<br>{}'.format(
                len(received), ' is' if len(received) <= 1 else 's are',
                args.host, '<br>'.join(
                    [f'{x} <= {received[x]}' for x in sorted(received.keys())]))
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/html': f'<div class="sos_hint">{msg}</div>'
                    }
                })
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to retrieve {", ".join(args.items)}: {e}')

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            return self.sos_kernel.notify_error(e)
        self.handle_magic_pull(args)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Push_Magic(SoS_Magic):
    name = 'push'

    def __init__(self, kernel):
        super(Push_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            'push',
            description='''Push local files or directory to a remote host''')
        parser.add_argument(
            'items',
            nargs='+',
            help='''Files or directories to be sent
            to remote host. The location of remote files are determined by "path_map"
            determined by "paths" definitions of local and remote hosts.''')
        parser.add_argument(
            '-t',
            '--to',
            dest='host',
            help='''Remote host to which the files will be sent. SoS will list all
            configured queues if no such key is defined''')
        parser.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.add_argument(
            '-v',
            '--verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        parser.error = self._parse_error
        return parser

    def handle_magic_push(self, args):
        from sos.hosts import Host
        load_config_files(args.config)
        try:
            host = Host(args.host)
            #
            sent = host.send_to_host(args.items)
            #
            msg = '{} item{} sent to {}:<br>{}'.format(
                len(sent), ' is' if len(sent) <= 1 else 's are', args.host,
                '<br>'.join([f'{x} => {sent[x]}' for x in sorted(sent.keys())]))
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/html': f'<div class="sos_hint">{msg}</div>'
                    }
                })
        except Exception as e:
            self.sos_kernel.warn(f'Failed to send {", ".join(args.items)}: {e}')

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            return self.sos_kernel.notify_error(e)
        self.handle_magic_push(args)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Put_Magic(SoS_Magic):
    name = 'put'

    def __init__(self, kernel):
        super(Put_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%put',
            description='''Put specified variables in the subkernel to another
            kernel, which is by default the SoS kernel.''')
        parser.add_argument(
            '--to',
            dest='__to__',
            help='''Name of kernel from which the variables will be obtained.
                Default to the SoS kernel.''')
        parser.add_argument(
            'vars', nargs='*', help='''Names of SoS variables''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            return self.sos_kernel.notify_error(e)
        try:
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        finally:
            self.sos_kernel.put_vars_to(args.vars, args.__to__, explicit=True)


class Render_Magic(SoS_Magic):
    name = 'render'

    def __init__(self, kernel):
        super(Render_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%render',
            description='''Treat the output of a SoS cell as another format, default to markdown.'''
        )
        parser.add_argument(
            'msg_type',
            default='stdout',
            choices=['stdout', 'text'],
            nargs='?',
            help='''Message type to capture, default to standard output. In terms of Jupyter message
                        types, "stdout" refers to "stream" message with "stdout" type, and "text" refers to
                        "display_data" message with "text/plain" type.''')
        parser.add_argument(
            '--as',
            dest='as_type',
            default='Markdown',
            nargs='?',
            help='''Format to render output of cell, default to Markdown, but can be any
            format that is supported by the IPython.display module such as HTML, Math, JSON,
            JavaScript and SVG.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        try:
            self.sos_kernel._meta['capture_result'] = []
            self.sos_kernel._meta['render_result'] = args.as_type
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        finally:
            content = ''
            if args.msg_type == 'stdout':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'stream' and msg[1]['name'] == 'stdout':
                        content += msg[1]['text']
            elif args.msg_type == 'text':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[
                            1] and 'text/plain' in msg[1]['data']:
                        content += msg[1]['data']['text/plain']
            try:
                if content:
                    format_dict, md_dict = self.sos_kernel.format_obj(
                        self.sos_kernel.render_result(content))
                    self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                                  'display_data', {
                                                      'metadata': md_dict,
                                                      'data': format_dict
                                                  })
            finally:
                self.sos_kernel._meta['capture_result'] = None
                self.sos_kernel._meta['render_result'] = False


class Runfile_Magic(SoS_Magic):
    name = 'runfile'

    def __init__(self, kernel):
        super(Runfile_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%runfile',
            description='''Execute an external SoS script, which is identical to
            run !sos run script but allows the display of task and workflow status
            in notebook. It also accepts default parameters of %set magic.''')
        parser.add_argument('script', help='''Script to be executed.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        if options.strip().endswith('&'):
            self.sos_kernel._meta['workflow_mode'] = 'nowait'
            options = options[:-1]
        else:
            self.sos_kernel._meta['workflow_mode'] = 'wait'

        parser = self.get_parser()
        try:
            args, run_options = parser.parse_known_args(shlex.split(options))
        except SystemExit:
            return

        self.sos_kernel.options = ' '.join(run_options)
        try:
            if os.path.isfile(os.path.expanduser(args.script)):
                if args.script.endswith('.ipynb'):
                    from sos.converter import extract_workflow
                    content = extract_workflow(os.path.expanduser(args.script))
                else:
                    with open(os.path.expanduser(args.script), 'r') as script:
                        content = script.read()
            elif os.path.isfile(os.path.expanduser(args.script + '.sos')):
                with open(os.path.expanduser(args.script + '.sos'),
                          'r') as script:
                    content = script.read()
            elif os.path.isfile(os.path.expanduser(args.script + '.ipynb')):
                from sos.converter import extract_workflow
                content = extract_workflow(
                    os.path.expanduser(args.script + '.ipynb'))
            else:
                raise RuntimeError(
                    f'{args.script}, {args.script}.sos or {args.script}.ipynb) does not exist.'
                )

            if self.sos_kernel.kernel != 'SoS':
                self.sos_kernel.switch_kernel('SoS')

            ret = self.sos_kernel._do_execute(content, silent, store_history,
                                              user_expressions, allow_stdin)
            if ret['status'] == 'error':
                return ret
        except Exception as e:
            self.sos_kernel.warn(f'Failed to execute workflow: {e}')
            raise
        finally:
            self.sos_kernel._meta['workflow_mode'] = False
            self.sos_kernel.options = ''
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Revisions_Magic(SoS_Magic):
    name = 'revisions'

    def __init__(self, kernel):
        super(Revisions_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%revision',
            description='''Revision history of the document, parsed from the log
            message of the notebook if it is kept in a git repository. Additional parameters to "git log" command
            (e.g. -n 5 --since --after) could be specified to limit the revisions to display.'''
        )
        parser.add_argument(
            '-s',
            '--source',
            nargs='?',
            default='',
            help='''Source URL to to create links for revisions.
            SoS automatically parse source URL of the origin and provides variables "repo" for complete origin
            URL without trailing ".git" (e.g. https://github.com/vatlab/sos-notebook), "path" for complete
            path name (e.g. src/document/doc.ipynb), "filename" for only the name of the "path", and "revision"
            for revisions. Because sos interpolates command line by default, variables in URL template should be
            included with double braceses (e.g. --source {{repo}}/blob/{{revision}}/{{path}})). If this option is
            provided without value and the document is hosted on github, a default template will be provided.'''
        )
        parser.add_argument(
            '-l',
            '--links',
            nargs='+',
            help='''Name and URL or additional links for related
            files (e.g. --links report URL_to_repo ) with URL interpolated as option --source.'''
        )
        parser.error = self._parse_error
        return parser

    def handle_magic_revisions(self, args, unknown_args):
        filename = self.sos_kernel._meta['notebook_name'] + '.ipynb'
        path = self.sos_kernel._meta['notebook_path']
        revisions = subprocess.check_output(
            ['git', 'log'] + unknown_args +
            ['--date=short', '--pretty=%H!%cN!%cd!%s', '--', filename])
        revisions = revisions.decode().splitlines()
        if not revisions:
            return
        # args.source is None for --source without option
        if args.source != '' or args.links:
            # need to determine origin etc for interpolation
            try:
                origin = subprocess.check_output(
                    ['git', 'ls-remote', '--get-url',
                     'origin']).decode().strip()
                repo = origin[:-4] if origin.endswith('.git') else origin
            except Exception as e:
                repo = ''
                env.log_to_file('MAGIC', f'Failed to get repo URL: {e}')
            if args.source is None:
                if 'github.com' in repo:
                    args.source = '{repo}/blob/{revision}/{path}'
                    env.log_to_file(
                        'MAGIC',
                        f"source is set to {args.source} with repo={repo}")
                else:
                    args.source = ''
                    self.sos_kernel.warn(
                        f'A default source URL is unavailable for repository {repo}'
                    )
        text = '''
        <table class="revision_table">
        <tr>
        <th>Revision</th>
        <th>Author</th>
        <th>Date</th>
        <th>Message</th>
        <tr>
        '''
        for line in revisions:
            fields = line.split('!', 3)
            revision = fields[0]
            fields[0] = f'<span class="revision_id">{fields[0][:7]}<span>'
            if args.source != '':
                # source URL
                URL = interpolate(
                    args.source, {
                        'revision': revision,
                        'repo': repo,
                        'filename': filename,
                        'path': path
                    })
                fields[0] = f'<a target="_blank" href="{URL}">{fields[0]}</a>'
            links = []
            if args.links:
                for i in range(len(args.links) // 2):
                    name = args.links[2 * i]
                    if len(args.links) == 2 * i + 1:
                        continue
                    URL = interpolate(
                        args.links[2 * i + 1], {
                            'revision': revision,
                            'repo': repo,
                            'filename': filename,
                            'path': path
                        })
                    links.append(f'<a target="_blank" href="{URL}">{name}</a>')
            if links:
                fields[0] += ' (' + ', '.join(links) + ')'
            text += '<tr>' + \
                '\n'.join(f'<td>{x}</td>' for x in fields) + '</tr>'
        text += '</table>'
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                      'display_data', {
                                          'metadata': {},
                                          'data': {
                                              'text/html': text
                                          }
                                      })

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, True)
        parser = self.get_parser()
        try:
            args, unknown_args = parser.parse_known_args(shlex.split(options))
        except SystemExit:
            return
        try:
            self.handle_magic_revisions(args, unknown_args)
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to retrieve revisions of notebook: {e}')
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Run_Magic(SoS_Magic):
    name = 'run'

    def __init__(self, kernel):
        super(Run_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%run',
            description='''Execute the current cell with specified command line
            arguments. If the magic ends with "&", it will be sent
            to a queue to be executed sequentially.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        # there can be multiple %run magic, but there should not be any other magics
        run_code = code
        run_options = []
        while True:
            if self.pattern.match(run_code):
                options, run_code = self.get_magic_and_code(run_code, False)
                run_options.append(options)
            else:
                break
        #
        if not run_code.strip():
            parser = self.get_parser()
            try:
                args, unknown_args = parser.parse_known_args(
                    shlex.split(options))
            except SystemExit:
                return

        # if there are more magics after %run, they will be ignored so a warning
        # is needed.
        if run_code.lstrip().startswith('%') and not any(
                run_code.lstrip().startswith(x) for x in ('%include', '%from')):
            self.sos_kernel.warn(
                f'Magic {run_code.split()[0]} after magic %run will be ignored.'
            )

        if not any(
                SOS_SECTION_HEADER.match(line)
                for line in run_code.splitlines()):
            run_code = '[default]\n' + run_code
        # now we need to run the code multiple times with each option
        for options in run_options:
            if options.strip().endswith('&'):
                self.sos_kernel._meta['workflow_mode'] = 'nowait'
                options = options[:-1]
            else:
                self.sos_kernel._meta['workflow_mode'] = 'wait'
            self.sos_kernel.options = options
            try:
                # %run is executed in its own namespace
                env.log_to_file('MAGIC', f'Executing\n{run_code}')
                if self.sos_kernel.kernel != 'SoS':
                    self.sos_kernel.switch_kernel('SoS')

                ret = self.sos_kernel._do_execute(run_code, silent,
                                                  store_history,
                                                  user_expressions, allow_stdin)
            except Exception as e:
                self.sos_kernel.warn(f'Failed to execute workflow: {e}')
                raise
            finally:
                self.sos_kernel._meta['workflow_mode'] = False
                self.sos_kernel.options = ''
        return ret


class Sandbox_Magic(SoS_Magic):
    name = 'sandbox'

    def __init__(self, kernel):
        super(Sandbox_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%sandbox',
            description='''Execute content of a cell in a temporary directory
                with fresh dictionary (by default).''')
        parser.add_argument(
            '-d',
            '--dir',
            help='''Execute workflow in specified directory. The directory
                will be created if does not exist, and will not be removed
                after the completion. ''')
        parser.add_argument(
            '-k',
            '--keep-dict',
            action='store_true',
            help='''Keep current sos dictionary.''')
        parser.add_argument(
            '-e',
            '--expect-error',
            action='store_true',
            help='''If set, expect error from the excution and report
                success if an error occurs.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        import tempfile
        import shutil
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        self.in_sandbox = True
        try:
            old_dir = os.getcwd()
            if args.dir:
                args.dir = os.path.expanduser(args.dir)
                if not os.path.isdir(args.dir):
                    os.makedirs(args.dir)
                env.exec_dir = os.path.abspath(args.dir)
                os.chdir(args.dir)
            else:
                new_dir = tempfile.mkdtemp()
                env.exec_dir = os.path.abspath(new_dir)
                os.chdir(new_dir)
            if not args.keep_dict:
                old_dict = env.sos_dict
                env.sos_dict._dict.clear()
            ret = self.sos_kernel._do_execute(remaining_code, silent,
                                              store_history, user_expressions,
                                              allow_stdin)
            if args.expect_error and ret['status'] == 'error':
                # self.sos_kernel.warn('\nSandbox execution failed.')
                return {
                    'status': 'ok',
                    'payload': [],
                    'user_expressions': {},
                    'execution_count': self.sos_kernel._execution_count
                }
            else:
                return ret
        finally:
            if not args.keep_dict:
                env.sos_dict = old_dict
            os.chdir(old_dir)
            if not args.dir:
                shutil.rmtree(new_dir)
            self.in_sandbox = False
            # env.exec_dir = old_dir


class Save_Magic(SoS_Magic):
    name = 'save'

    def __init__(self, kernel):
        super(Save_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%save',
            description='''Save the content of the cell to specified file. It
            ignores magic lines after the %save magic unless a blank line is used
            to separate the magics and the content to be saved.''')
        parser.add_argument(
            'filename', help='''Filename of saved report or script.''')
        parser.add_argument(
            '-r',
            '--run',
            action='store_true',
            help='''Continue to execute the cell once content is saved.''')
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help='''If destination file already exists, overwrite it.''')
        parser.add_argument(
            '-a',
            '--append',
            action='store_true',
            help='''If destination file already exists, append to it.''')
        parser.add_argument(
            '-x',
            '--set-executable',
            dest="setx",
            action='store_true',
            help='''Set `executable` permission to saved script.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):

        # if sos kernel ...
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
            filename = os.path.expanduser(args.filename)
            if os.path.isfile(filename) and not args.force:
                raise ValueError(
                    f'{filename} already exists. Use "-f" if you would like to overwrite this file.'
                )

            with open(filename, 'a' if args.append else 'w') as script:
                line_no = -1
                for line in remaining_code.splitlines():
                    if line.startswith('%') and line_no < 0:
                        continue
                    if line_no <= 0 and not line.strip():
                        # started
                        line_no = 0
                        continue
                    line_no += 1
                    script.write(line + '\n')

            if args.setx:
                import stat
                os.chmod(filename, os.stat(filename).st_mode | stat.S_IEXEC)

            about_run = "" if args.run else ", use option -r to also execute the cell."
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/plain':
                            f'Cell content saved to {filename}{about_run}\n',
                        'text/html':
                            f'<div class="sos_hint">Cell content saved to <a href="{filename}" target="_blank">{filename}</a>{about_run}</div>'
                    }
                })
            if args.run:
                return self.sos_kernel._do_execute(remaining_code, silent,
                                                   store_history,
                                                   user_expressions,
                                                   allow_stdin)
            else:
                return None
        except Exception as e:
            return self.sos_kernel.notify_error(e)


class SessionInfo_Magic(SoS_Magic):
    name = 'sessioninfo'

    def __init__(self, kernel):
        super(SessionInfo_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%sessioninfo',
            description='''List the session info of all subkernels, and information
            stored in variable sessioninfo''')
        parser.add_argument(
            '-w',
            '--with',
            dest='__with__',
            help='''Name of variable that contains extra information to be appended.
                This variable should be a dictionary, with keys being the section headers
                and items being the session information, which can be a string, a list of
                strings, a dictionary, or a list of `(key, value)` pairs. Encoded strings
                (bytes) are acceptable in places of strings. ''')
        parser.error = self._parse_error
        return parser

    def handle_sessioninfo(self, args):
        #
        from sos.utils import loaded_modules
        result = OrderedDict()
        #
        result['SoS'] = [('SoS Version', __version__)]
        result['SoS'].extend(loaded_modules(env.sos_dict))
        #
        cur_kernel = self.sos_kernel.kernel
        try:
            for kernel in self.sos_kernel.kernels.keys():
                kinfo = self.sos_kernel.subkernels.find(kernel)
                self.sos_kernel.switch_kernel(kernel)
                result[kernel] = [('Kernel', kinfo.kernel),
                                  ('Language', kinfo.language)]
                if kernel not in self.sos_kernel.supported_languages:
                    continue
                lan = self.sos_kernel.supported_languages[kernel]
                if hasattr(lan, 'sessioninfo'):
                    try:
                        sinfo = lan(self.sos_kernel, kinfo.kernel).sessioninfo()
                        if isinstance(sinfo, str):
                            result[kernel].append([sinfo])
                        elif isinstance(sinfo, dict):
                            result[kernel].extend(list(sinfo.items()))
                        elif isinstance(sinfo, list):
                            result[kernel].extend(sinfo)
                        else:
                            self.sos_kernel.warn(
                                f'Unrecognized session info: {sinfo}')
                    except Exception as e:
                        self.sos_kernel.warn(
                            f'Failed to obtain sessioninfo of kernel {kernel}: {e}'
                        )
        finally:
            self.sos_kernel.switch_kernel(cur_kernel)
        #
        if args.__with__:
            if args.__with__ not in env.sos_dict:
                self.sos_kernel.warn(
                    f'Variable {args.__with__} not defined for additional session information.'
                )
            result.update(env.sos_dict[args.__with__])
        #
        res = ''
        for key, items in result.items():
            res += f'<p class="session_section">{key}</p>\n'
            res += '<table class="session_info">\n'
            if isinstance(items, (str, bytes)):
                items = [items]
            elif isinstance(items, dict):
                items = list(items.items())
            for item in items:
                res += '<tr>\n'
                if isinstance(item, (str, bytes)):
                    res += f'<td colspan="2"><pre>{self.prepare_string(item)}</pre></td>\n'
                elif isinstance(item, Sequence):
                    if len(item) == 1:
                        res += f'<td colspan="2"><pre>{self.prepare_string(item[0])}</pre></td>\n'
                    elif len(item) == 2:
                        res += f'<th>{self.prepare_string(item[0])}</th><td><pre>{self.prepare_string(item[1])}</pre></td>\n'
                    else:
                        self.sos_kernel.warn(
                            f'Invalid session info item of type {item.__class__.__name__}: {short_repr(item)}'
                        )
                else:
                    self.sos_kernel.warn(
                        f'Invalid session info item of type {item.__class__.__name__}: {short_repr(item)}'
                    )
                res += '</tr>\n'
            res += '</table>\n'
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                      'display_data', {
                                          'metadata': {},
                                          'data': {
                                              'text/html': res
                                          }
                                      })

    def prepare_string(self, item):
        '''trim string, and decode if needed'''
        if isinstance(item, bytes):
            try:
                item = item.decode('utf-8')
            except Exception:
                return str(item)
        return item.strip()

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        self.handle_sessioninfo(args)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Set_Magic(SoS_Magic):
    name = 'set'

    def __init__(self, kernel):
        super(Set_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        self.sos_kernel.warn(
            f'Magic %set is deprecated (vatlab/sos-notebook#231)')
        # self.sos_kernel.options will be set to inflence the execution of remaing_code
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Shutdown_Magic(SoS_Magic):
    name = 'shutdown'

    def __init__(self, kernel):
        super(Shutdown_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%shutdown',
            description='''Shutdown or restart specified subkernel''')
        parser.add_argument(
            'kernel',
            nargs='?',
            help='''Name of the kernel to be restarted, default to the
            current running kernel.''')
        parser.add_argument(
            '-r',
            '--restart',
            action='store_true',
            help='''Restart the kernel''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        self.sos_kernel.shutdown_kernel(
            args.kernel if args.kernel else self.sos_kernel.kernel,
            args.restart)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class SoSRun_Magic(SoS_Magic):
    name = 'sosrun'

    def __init__(self, kernel):
        super(SoSRun_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%sosrun',
            description='''Execute the entire notebook with steps consisting of SoS
            cells (cells with SoS kernel) with section header, with specified command
            line arguments. Arguments set by magic %set will be appended at the
            end of command line. If the magic ends with "&", it will be sent
            to a queue to be executed sequentially.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            # only show message with %sosrun -h, not with any other parameter because
            # the pipeline can have help message
            if options.strip() == '-h':
                parser.parse_args([options])
        except SystemExit:
            return
        if options.strip().endswith('&'):
            self.sos_kernel._meta['workflow_mode'] = 'nowait'
            options = options[:-1]
        else:
            self.sos_kernel._meta['workflow_mode'] = 'wait'
        self.sos_kernel.options = options
        try:
            if self.sos_kernel.kernel != 'SoS':
                self.sos_kernel.switch_kernel('SoS')
            # self.sos_kernel.send_frontend_msg('preview-workflow', self.sos_kernel._meta['workflow'])
            if not self.sos_kernel._meta['workflow']:
                self.sos_kernel.warn(
                    'Nothing to execute (notebook workflow is empty).')
            else:
                self.sos_kernel._do_execute(self.sos_kernel._meta['workflow'],
                                            silent, store_history,
                                            user_expressions, allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(f'Failed to execute workflow: {e}')
            raise
        finally:
            self.sos_kernel._meta['workflow_mode'] = False
            self.sos_kernel.options = ''
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class SoSSave_Magic(SoS_Magic):
    name = 'sossave'

    def __init__(self, kernel):
        super(SoSSave_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%sossave',
            description='''Save the jupyter notebook as workflow (consisting of all sos
            steps defined in cells starting with section header) or a HTML report to
            specified file.''')
        parser.add_argument(
            'filename',
            nargs='?',
            help='''Filename of saved report or script. Default to notebookname with file
            extension determined by option --to.''')
        parser.add_argument(
            '-t',
            '--to',
            dest='__to__',
            choices=['sos', 'html'],
            help='''Destination format, default to sos.''')
        parser.add_argument(
            '-c',
            '--commit',
            action='store_true',
            help='''Commit the saved file to git directory using command
            git commit FILE''')
        parser.add_argument(
            '-m',
            '--message',
            help='''Message for git commit. Default to "save FILENAME"''')
        parser.add_argument(
            '-p',
            '--push',
            action='store_true',
            help='''Push the commit with command "git push"''')
        parser.add_argument(
            '-f',
            '--force',
            action='store_true',
            help='''If destination file already exists, overwrite it.''')
        parser.add_argument(
            '-x',
            '--set-executable',
            dest="setx",
            action='store_true',
            help='''Set `executable` permission to saved script.''')
        parser.add_argument(
            '--template',
            default='default-sos-template',
            help='''Template to generate HTML output. The default template is a
            template defined by configuration key default-sos-template, or
            sos-report-toc if such a key does not exist.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        self.sos_kernel.warn(
            'Magic %sossave is depcated. Please use %convert instead.')
        # get the saved filename
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
            if args.filename:
                filename = args.filename
                if filename.lower().endswith('.html'):
                    if args.__to__ is None:
                        ftype = 'html'
                    elif args.__to__ != 'html':
                        self.sos_kernel.warn(
                            f'%sossave to an .html file in {args.__to__} format'
                        )
                        ftype = args.__to__
                else:
                    ftype = 'sos'
            else:
                ftype = args.__to__ if args.__to__ else 'sos'
                filename = self.sos_kernel._meta['notebook_name'] + '.' + ftype

            filename = os.path.expanduser(filename)

            if os.path.isfile(filename) and not args.force:
                raise ValueError(
                    f'Cannot overwrite existing output file {filename}')
            # self.sos_kernel.send_frontend_msg('preview-workflow', self.sos_kernel._meta['workflow'])
            if ftype == 'sos':
                with open(filename, 'w') as script:
                    script.write(self.sos_kernel._meta['workflow'])
                if args.setx:
                    import stat
                    os.chmod(filename, os.stat(filename).st_mode | stat.S_IEXEC)
            else:
                # convert to sos report
                from .converter import NotebookToHTMLConverter
                arg = argparse.Namespace()
                if args.template == 'default-sos-template':
                    cfg = load_config_files()
                    if 'default-sos-template' in cfg:
                        arg.template = cfg['default-sos-template']
                    else:
                        arg.template = 'sos-report-toc'
                else:
                    arg.template = args.template
                arg.view = False
                arg.execute = False
                NotebookToHTMLConverter().convert(
                    self.sos_kernel._meta['notebook_name'] + '.ipynb',
                    filename,
                    sargs=arg,
                    unknown_args=[])

            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/plain':
                            f'Notebook saved to {filename}\n',
                        'text/html':
                            f'<div class="sos_hint">Notebook saved to <a href="{filename}" target="_blank">{filename}</a></div>'
                    }
                })
            #
            if args.commit:
                self.run_shell_command({
                    'git', 'commit', filename, '-m',
                    args.message if args.message else f'save {filename}'
                })
            if args.push:
                self.run_shell_command(['git', 'push'])
            return
        except Exception as e:
            return self.sos_kernel.notify_error(e)


class Task_Magic(SoS_Magic):
    name = 'task'

    def __init__(self, kernel):
        super(Task_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%task',
            description='''Get information on specified task. By default
            sos would query against all running task queues but it would
            start a task queue and query status if option -q is specified.
            ''')
        subparsers = parser.add_subparsers(help='actions')
        status = subparsers.add_parser('status', help='task status')
        status.add_argument(
            'tasks',
            nargs='*',
            help='''ID of the task. All tasks
            that are releted to the workflow executed under the current directory
            will be checked if unspecified. There is no need to specify compelete
            task IDs because SoS will match specified name with tasks starting with
            these names.''')
        status.add_argument(
            '-q',
            '--queue',
            help='''Check the status of job on specified tasks queue or remote host
            if the tasks . The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found.''')
        status.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global sos config.yml files.'''
        )
        status.add_argument(
            '-a', '--all', action='store_true', help=argparse.SUPPRESS)
        status.add_argument(
            '-v',
            dest='verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        status.add_argument(
            '-t',
            '--tags',
            nargs='*',
            help='''Only list tasks with
            one of the specified tags.''')
        status.add_argument(
            '-s',
            '--status',
            nargs='*',
            help='''Display tasks with
            one of the specified status.''')
        status.add_argument(
            '--age',
            help='''Limit to tasks that are created more than
            (default) or within specified age. Value of this parameter can be in units
            s (second), m (minute), h (hour), or d (day, default), or in the foramt of
            HH:MM:SS, with optional prefix + for older (default) and - for newer than
            specified age.''')
        status.add_argument(
            '--html', action='store_true', help=argparse.SUPPRESS)
        status.add_argument(
            '--numeric-times', action='store_true', help=argparse.SUPPRESS)
        status.set_defaults(func=self.status)

        execute = subparsers.add_parser('execute', help='execute task')
        execute.add_argument(
            'tasks',
            nargs='*',
            help='''ID of the tasks to be removed.
            There is no need to specify compelete task IDs because SoS will match specified
            name with tasks starting with these names. If no task ID is specified,
            all tasks related to specified workflows (option -w) will be removed.'''
        )
        execute.add_argument(
            '-q',
            '--queue',
            help='''Remove tasks on specified tasks queue or remote host
            if the tasks . The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found. ''')
        execute.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global sos config.yml files.'''
        )
        execute.add_argument(
            '-v',
            dest='verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        execute.set_defaults(func=self.execute)

        kill = subparsers.add_parser(
            'kill', help='kill single task or tasks with the same tags')
        kill.add_argument(
            'tasks',
            nargs='*',
            help='''IDs of the tasks
            that will be killed. There is no need to specify compelete task IDs because
            SoS will match specified name with tasks starting with these names.'''
        )
        kill.add_argument(
            '-a',
            '--all',
            action='store_true',
            help='''Kill all tasks in local or specified remote task queue''')
        kill.add_argument(
            '-q',
            '--queue',
            help='''Kill jobs on specified tasks queue or remote host
            if the tasks . The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found.''')
        kill.add_argument(
            '-t',
            '--tags',
            nargs='*',
            help='''Only kill tasks with
            one of the specified tags.''')
        kill.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global sos config.yml files.'''
        )
        kill.add_argument(
            '-v',
            '--verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        kill.set_defaults(func=self.kill)

        purge = subparsers.add_parser('purge', help='kill and purge task')
        purge.add_argument(
            'tasks',
            nargs='*',
            help='''ID of the tasks to be removed.
            There is no need to specify compelete task IDs because SoS will match specified
            name with tasks starting with these names. If no task ID is specified,
            all tasks related to specified workflows (option -w) will be removed.'''
        )
        group = parser.add_mutually_exclusive_group(required=False)
        group.add_argument(
            '-a',
            '--all',
            action='store_true',
            help='''Clear all task information on local or specified remote task queue,
            including tasks created by other workflows.''')
        group.add_argument(
            '--age',
            help='''Remove all tasks that are created more than
            (default) or within specified age. Value of this parameter can be in units
            s (second), m (minute), h (hour), or d (day, default), or in the foramt of
            HH:MM:SS, with optional prefix + for older (default) and - for newer than
            specified age.''')
        group.add_argument(
            '-s',
            '--status',
            nargs='+',
            help='''Remove all tasks with specified status, which can be pending, submitted,
                running, completed, failed, and aborted. One of more status can be specified.'''
        )
        group.add_argument(
            '-t',
            '--tags',
            nargs='*',
            help='''Remove all tsks with one of the specified tags.''')
        purge.add_argument(
            '-q',
            '--queue',
            help='''Remove tasks on specified tasks queue or remote host
            if the tasks . The queue can be defined in global or local sos
            configuration file, or a file specified by option  --config. A host is
            assumed to be a remote machine with process type if no configuration
            is found. ''')
        purge.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global sos config.yml files.'''
        )
        purge.add_argument(
            '-v',
            dest='verbosity',
            type=int,
            choices=range(5),
            default=2,
            help='''Output error (0), warning (1), info (2), and debug (3)
                information to standard output (default to 2).''')
        purge.set_defaults(func=self.purge)
        parser.error = self._parse_error
        return parser

    def status(self, args):
        from sos.hosts import Host
        try:
            host = Host(args.queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queue {}: {}'.format(
                args.queue, e))
            return

        result = host._task_engine.query_tasks(
            tasks=args.tasks,
            check_all=not args.tasks,
            verbosity=2,
            html=len(args.tasks) == 1,
            numeric_times=False,
            age=args.age,
            tags=args.tags,
            status=args.status)
        # now, there is a possibility that the status of the task is different from what
        # task engine knows (e.g. a task is runfile outside of jupyter). In this case, since we
        # already get the status, we should update the task engine...
        #
        # HTML output
        if len(args.tasks) == 1:
            self.sos_kernel.send_frontend_msg('display_data', {
                'metadata': {},
                'data': {
                    'text/plain': result,
                    'text/html': result
                }
            })
            # <tr><th align="right"  width="30%">Status</th><td align="left"><div class="one_liner">completed</div></td></tr>
            status = result.split('>Status<', 1)[-1].split('</div',
                                                           1)[0].split('>')[-1]
            self.sos_kernel.send_frontend_msg(
                'task_status', {
                    'update_only': True,
                    'queue': host.alias,
                    'task_id': args.tasks[0],
                    'status': status,
                })
        else:
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                          'stream', {
                                              'name': 'stdout',
                                              'text': result
                                          })
            # regular output
            for line in result.split('\n'):
                if not line.strip():
                    continue
                try:
                    # return creation time, start time, and duration
                    tid, tags, _, tst = line.split('\t')
                    self.sos_kernel.send_frontend_msg(
                        'task_status', {
                            'update_only': True,
                            'queue': host.alias,
                            'task_id': tid,
                            'status': tst,
                            'tags': tags
                        })
                except Exception as e:
                    env.logger.warning(
                        f'Unrecognized response "{line}" ({e.__class__.__name__}): {e}'
                    )

    def execute(self, args):
        from sos.hosts import Host
        try:
            host = Host(args.queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queue {}: {}'.format(
                args.queue, e))
            return
        for task in args.tasks:
            host._task_engine.submit_task(task)
            self.sos_kernel.send_frontend_msg(
                'task_status', {
                    'update_only': True,
                    'queue': args.queue,
                    'task_id': task,
                    'status': 'pening',
                })

    def kill(self, args):
        # kill specified task
        from sos.hosts import Host
        try:
            host = Host(args.queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queue {}: {}'.format(
                args.queue, e))
            return
        if args.tasks:
            # kill specified task
            ret = host._task_engine.kill_tasks(args.tasks)
        elif args.tags:
            ret = host._task_engine.kill_tasks([], tags=args.tags)
        else:
            self.sos_kernel.warn(
                'Please specify either a list of task or a tag')
            return
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream', {
            'name': 'stdout',
            'text': ret
        })
        for line in ret.split('\n'):
            if not line.strip():
                continue
            try:
                # return creation time, start time, and duration
                tid, tst = line.split('\t')
                self.sos_kernel.send_frontend_msg(
                    'task_status', {
                        'update_only': True,
                        'queue': args.queue,
                        'task_id': tid,
                        'status': tst
                    })
            except Exception as e:
                env.logger.warning(
                    f'Unrecognized response "{line}" ({e.__class__.__name__}): {e}'
                )

    def purge(self, args):
        # kill specified task
        from sos.hosts import Host
        try:
            host = Host(args.queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queue {}: {}'.format(
                args.queue, e))
            return
        ret = host._task_engine.purge_tasks(
            tasks=args.tasks,
            purge_all=not args.tasks and
            (args.all or args.age or args.tags or args.status),
            age=args.age,
            status=args.status,
            tags=args.tags,
            verbosity=env.verbosity)
        if ret:
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket,
                                          'stream', {
                                              'name': 'stdout',
                                              'text': ret
                                          })
        else:
            self.sos_kernel.send_response(
                self.sos_kernel.iopub_socket, 'stream', {
                    'name': 'stderr',
                    'text': 'No matching task to purge'
                })
        if args.tasks:
            for task in args.tasks:
                self.sos_kernel.send_frontend_msg(
                    'task_status', {
                        'update_only': True,
                        'queue': args.queue,
                        'task_id': task,
                        'status': 'purged'
                    })
        else:
            for tag in args.tags:
                self.sos_kernel.send_frontend_msg(
                    'task_status', {
                        'update_only': True,
                        'queue': args.queue,
                        'tag': args.tags,
                        'status': 'purged'
                    })

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        load_config_files(args.config)

        args.func(args)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Tasks_Magic(SoS_Magic):
    name = 'tasks'

    def __init__(self, kernel):
        super(Tasks_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%tasks',
            description='''Show a list of tasks from specified queue''')
        parser.add_argument('tasks', nargs='*', help='ID of tasks')
        parser.add_argument(
            '-s',
            '--status',
            nargs='*',
            help='''Display tasks of specified status. Default to all.''')
        parser.add_argument(
            '-q',
            '--queue',
            help='''Task queue on which the tasks are retrived.''')
        parser.add_argument(
            '--age',
            help='''Limit to tasks that is created more than
            (default) or within specified age. Value of this parameter can be in units
            s (second), m (minute), h (hour), or d (day, default), with optional
            prefix + for older (default) and - for younder than specified age.'''
        )
        parser.add_argument(
            '-c',
            '--config',
            help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.error = self._parse_error
        return parser

    def handle_tasks(self, tasks, queue='localhost', status=None, age=None):
        from sos.hosts import Host
        try:
            host = Host(queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queue {}: {}'.format(queue, e))
            return
        # get all tasks
        for tid, tst, tdt in host._task_engine.monitor_tasks(
                tasks, status=status, age=age):
            self.sos_kernel.send_frontend_msg(
                'task_status', {
                    'cell_id': self.sos_kernel.cell_id,
                    'queue': queue,
                    'task_id': tid,
                    'status': tst
                })

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        load_config_files(args.config)
        self.handle_tasks(args.tasks, args.queue if args.queue else 'localhost',
                          args.status, args.age)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Toc_Magic(SoS_Magic):
    name = 'toc'

    def __init__(self, kernel):
        super(Toc_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        self.sos_kernel.warn('Magic %toc is deprecated.')
        options, remaining_code = self.get_magic_and_code(code, False)
        return self.sos_kernel._do_execute(remaining_code, silent,
                                           store_history, user_expressions,
                                           allow_stdin)


class Use_Magic(SoS_Magic):
    name = 'use'

    def __init__(self, kernel):
        super(Use_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%use',
            description='''Switch to an existing subkernel
            or start a new subkernel.''')
        parser.add_argument(
            'name',
            nargs='?',
            default='',
            help='''Displayed name of kernel to start (if no kernel with name is
            specified) or switch to (if a kernel with this name is already started).
            The name is usually a kernel name (e.g. %%use ir) or a language name
            (e.g. %%use R) in which case the language name will be used. One or
            more parameters --language or --kernel will need to be specified
            if a new name is used to start a separate instance of a kernel.''')
        parser.add_argument(
            '-k',
            '--kernel',
            help='''kernel name as displayed in the output of jupyter kernelspec
            list. Default to the default kernel of selected language (e.g. ir for
            language R.''')
        parser.add_argument(
            '-l',
            '--language',
            help='''Language extension that enables magics such as %%get and %%put
            for the kernel, which should be in the name of a registered language
            (e.g. R), or a specific language module in the format of
            package.module:class. SoS maitains a list of languages and kernels
            so this option is only needed for starting a new instance of a kernel.
            ''')
        parser.add_argument(
            '-c',
            '--color',
            help='''Background color of new or existing kernel, which overrides
            the default color of the language. A special value "default" can be
            used to reset color to default.''')
        parser.add_argument(
            '-r',
            '--restart',
            action='store_true',
            help='''Restart the kernel if it is running.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):

        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {
                'status': 'abort',
                'ename': e.__class__.__name__,
                'evalue': str(e),
                'traceback': [],
                'execution_count': self.sos_kernel._execution_count,
            }
        if args.restart and args.name in self.sos_kernel.kernels:
            self.shutdown_kernel(args.name)
            self.sos_kernel.warn(f'{args.name} is shutdown')
        try:
            self.sos_kernel.switch_kernel(args.name, None, args.kernel,
                                          args.language, args.color)
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        except Exception as e:
            return self.sos_kernel.notify_error(e)


class With_Magic(SoS_Magic):
    name = 'with'

    def __init__(self, kernel):
        super(With_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(
            prog='%with',
            description='''Use specified subkernel to evaluate current
            cell, with optional input and output variables''')
        parser.add_argument(
            'name',
            nargs='?',
            default='',
            help='''Name of an existing kernel.''')
        parser.add_argument(
            '-i',
            '--in',
            nargs='*',
            dest='in_vars',
            help='Input variables (variables to get from SoS kernel)')
        parser.add_argument(
            '-o',
            '--out',
            nargs='*',
            dest='out_vars',
            help='''Output variables (variables to put back to SoS kernel
            before switching back to the SoS kernel''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(shlex.split(options))
            except SystemExit:
                return
        except Exception as e:
            return self.sos_kernel.notify_error(e)

        original_kernel = self.sos_kernel.kernel
        try:
            self.sos_kernel.switch_kernel(args.name, args.in_vars)
        except Exception as e:
            return self.sos_kernel.notify_error(e)
        try:
            return self.sos_kernel._do_execute(remaining_code, silent,
                                               store_history, user_expressions,
                                               allow_stdin)
        finally:
            self.sos_kernel.switch_kernel(original_kernel, args.out_vars)
            self.sos_kernel.send_frontend_msg(
                'cell-kernel',
                [self.sos_kernel._meta['cell_id'], original_kernel])


class SoS_Magics(object):
    magics = [
        Command_Magic, Capture_Magic, Cd_Magic, Clear_Magic, ConnectInfo_Magic,
        Convert_Magic, Debug_Magic, Dict_Magic, Env_Magic, Expand_Magic,
        Get_Magic, Matplotlib_Magic, Preview_Magic, Pull_Magic, Paste_Magic,
        Push_Magic, Put_Magic, Render_Magic, Run_Magic, Runfile_Magic,
        Revisions_Magic, Save_Magic, Set_Magic, SessionInfo_Magic,
        Shutdown_Magic, SoSRun_Magic, SoSSave_Magic, Task_Magic, Toc_Magic,
        Sandbox_Magic, Use_Magic, With_Magic
    ]
    names = [x.name for x in magics if x.name != '!']

    def __init__(self, kernel=None):
        self._magics = {x.name: x(kernel) for x in self.magics}

    def get(self, name):
        return self._magics[name]

    def values(self):
        return self._magics.values()
