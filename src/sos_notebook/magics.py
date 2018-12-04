
import argparse
import fnmatch
import os
import pydoc
import re
import shlex
import subprocess
import sys
from collections import Sized, OrderedDict
from io import StringIO
from types import ModuleType

import pandas as pd
from IPython.core.display import HTML
from IPython.core.error import UsageError
from IPython.lib.clipboard import (ClipboardEmpty, osx_clipboard_get,
                                   tkinter_clipboard_get)
from jupyter_client import find_connection_file
from sos.eval import SoS_eval, interpolate
from sos.syntax import SOS_SECTION_HEADER
from sos.utils import env, pretty_size, short_repr, pexpect_run
from sos._version import  __version__


class SoS_Magic(object):
    name = 'BaseMagic'

    def __init__(self, kernel):
        self.sos_kernel = kernel
        self.pattern = re.compile(f'%{self.name}(\s|$)')

    def _interpolate_text(self, text, quiet=False):
        # interpolate command
        try:
            new_text = interpolate(text, local_dict=env.sos_dict._dict)
            if new_text != text and not quiet:
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                          {
                                              'metadata': {},
                                              'data': {
                                                  'text/html': HTML(
                                                      f'<div class="sos_hint">> {new_text.strip() + "<br>"}</div>').data}
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
                pexpect_run(cmd, shell=True,
                            win_width=40 if self.sos_kernel._meta['cell_id'] == "" else 80)
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
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Capture_Magic(SoS_Magic):
    name = 'capture'

    def __init__(self, kernel):
        super(Capture_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%capture',
                                         description='''Capture output (stdout) or output file from a subkernel
                                         as variable in SoS''')
        parser.add_argument('msg_type', nargs='?', default='stdout', choices=['stdout', 'stderr', 'text', 'markdown',
                                                                              'html', 'raw'],
                            help='''Message type to capture, default to standard output. In terms of Jupyter message
                        types, "stdout" refers to "stream" message with "stdout" type, "stderr" refers to "stream"
                        message with "stderr" type, "text", "markdown" and "html" refers to "display_data" message
                        with "text/plain", "text/markdown" and "text/html" type respectively. If "raw" is specified,
                        all returned messages will be returned in a list format.''')
        parser.add_argument('--as', dest='as_type', default='text', nargs='?', choices=('text', 'json', 'csv', 'tsv'),
                            help='''How to interpret the captured text. This only applicable to stdout, stderr and
                            text message type where the text from cell output will be collected. If this
                            option is given, SoS will try to parse the text as json, csv (comma separated text),
                             tsv (tab separated text), and store text (from text), Pandas DataFrame
                            (from csv or tsv), dict or other types (from json) to the variable.''')
        grp = parser.add_mutually_exclusive_group(required=False)
        grp.add_argument('-t', '--to', dest='__to__', metavar='VAR',
                         help='''Name of variable to which the captured content will be saved. If no varialbe is
                         specified, the return value will be saved to variable "__captured" and be displayed
                         at the side panel. ''')
        grp.add_argument('-a', '--append', dest='__append__', metavar='VAR',
                         help='''Name of variable to which the captured content will be appended.
                            This option is equivalent to --to if VAR does not exist. If VAR exists
                            and is of the same type of new content (str or dict or DataFrame), the
                            new content will be appended to VAR if VAR is of str (str concatenation),
                            dict (dict update), or DataFrame (DataFrame.append) types. If VAR is of
                            list type, the new content will be appended to the end of the list.''')
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
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
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
                    if msg[0] == 'display_data' and 'data' in msg[1] and 'text/plain' in msg[1]['data']:
                        content += msg[1]['data']['text/plain']
            elif args.msg_type == 'markdown':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[1] and 'text/markdown' in msg[1]['data']:
                        content += msg[1]['data']['text/markdown']
            elif args.msg_type == 'html':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[1] and 'text/html' in msg[1]['data']:
                        content += msg[1]['data']['text/html']
            else:
                args.as_type = 'raw'
                content = self.sos_kernel._meta['capture_result']

            if self.sos_kernel._debug_mode:
                self.sos_kernel.warn(
                    f'Captured {self.sos_kernel._meta["capture_result"][:40]}')
            if not args.as_type or args.as_type == 'text':
                if not isinstance(content, str):
                    self.sos_kernel.warn(
                        'Option --as is only available for message types stdout, stderr, and text.')
            elif args.as_type == 'json':
                import json
                try:
                    if isinstance(content, str):
                        content = json.loads(content)
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.')
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in JSON format, text returned: {e}')
            elif args.as_type == 'csv':
                try:
                    if isinstance(content, str):
                        with StringIO(content) as ifile:
                            content = pd.read_csv(ifile)
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.')
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in {args.as_type} format, text returned: {e}')
            elif args.as_type == 'tsv':
                try:
                    if isinstance(content, str):
                        with StringIO(content) as ifile:
                            content = pd.read_csv(ifile, sep='\t')
                    else:
                        self.sos_kernel.warn(
                            'Option --as is only available for message types stdout, stderr, and text.')
                except Exception as e:
                    self.sos_kernel.warn(
                        f'Failed to capture output in {args.as_type} format, text returned: {e}')
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
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}')
                elif isinstance(env.sos_dict[args.__append__], dict):
                    if isinstance(content, dict):
                        env.sos_dict[args.__append__].update(content)
                    else:
                        self.sos_kernel.warn(
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}')
                elif isinstance(env.sos_dict[args.__append__], pd.DataFrame):
                    if isinstance(content, pd.DataFrame):
                        env.sos_dict.set(
                            args.__append__, env.sos_dict[args.__append__].append(content))
                    else:
                        self.sos_kernel.warn(
                            f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}')
                elif isinstance(env.sos_dict[args.__append__], list):
                    env.sos_dict[args.__append__].append(content)
                else:
                    self.sos_kernel.warn(
                        f'Cannot append new content of type {type(content).__name__} to {args.__append__} of type {type(env.sos_dict[args.__append__]).__name__}')
            else:
                env.sos_dict.set('__captured', content)
                import pprint
                self.sos_kernel.send_frontend_msg('display_data',
                                              {'metadata': {},
                                               'data': {'text/plain': pprint.pformat(content)}
                                               })
        self.sos_kernel._meta['capture_result'] = None


class Cd_Magic(SoS_Magic):
    name = 'cd'

    def __init__(self, kernel):
        super(Cd_Magic, self).__init__(kernel)

    def handle_magic_cd(self, option):
        if not option:
            return
        to_dir = option.strip()
        try:
            os.chdir(os.path.expanduser(to_dir))
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                      {'name': 'stdout', 'text': os.getcwd()})
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
                        f'Current directory of kernel {kernel} is not changed: unsupported language')
                    continue
                lan = self.sos_kernel.supported_languages[kernel]
                if hasattr(lan, 'cd_command'):
                    try:
                        self.sos_kernel.switch_kernel(kernel)
                        cmd = interpolate(lan.cd_command, {'dir': to_dir})
                        self.sos_kernel.run_cell(
                            cmd, True, False, on_error=f'Failed to execute {cmd} in {kernel}')
                    except Exception as e:
                        self.sos_kernel.warn(
                            f'Current directory of kernel {kernel} is not changed: {e}')
                else:
                    self.sos_kernel.warn(
                        f'Current directory of kernel {kernel} is not changed: cd_command not defined')
        finally:
            self.sos_kernel.switch_kernel(cur_kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        self.handle_magic_cd(options)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Clear_Magic(SoS_Magic):
    name = 'clear'

    def __init__(self, kernel):
        super(Clear_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%clear',
                                         description='''Clear the output of the current cell, or the current
            active cell if executed in the sidepanel.''')
        parser.add_argument('-a', '--all', action='store_true',
                            help='''Clear all output or selected status or class of the current notebook.''')
        grp = parser.add_mutually_exclusive_group()
        grp.add_argument('-s', '--status', nargs='+',
                         help='''Clear tasks that match specifie status (e.g. completed).''')
        grp.add_argument('-c', '--class', nargs='+', dest='elem_class',
                         help='''Clear all HTML elements with specified classes (e.g. sos_hint)''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(options.split())
        except SystemExit:
            return
        # self.sos_kernel._meta['cell_id'] could be reset by _do_execute
        cell_id = self.sos_kernel._meta['cell_id']
        try:
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        finally:
            if self.sos_kernel._meta.get('batch_mode', False):
                return
            if args.status:
                status_style = [self.status_class[x] for x in args.status]
            else:
                status_style = None
            self.sos_kernel.send_frontend_msg(
                'clear-output', [cell_id, args.all, status_style, args.elem_class])


class ConnectInfo_Magic(SoS_Magic):
    name = 'connectinfo'

    def __init__(self, kernel):
        super(ConnectInfo_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        cfile = find_connection_file()
        with open(cfile) as conn:
            conn_info = conn.read()
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                  {'name': 'stdout', 'text': 'Connection file: {}\n{}'.format(cfile, conn_info)})
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Debug_Magic(SoS_Magic):
    name = 'debug'

    def __init__(self, kernel):
        super(Debug_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%debug',
                                         description='''Turn on or off debug information''')
        parser.add_argument('status', choices=['on', 'off'],
                            help='''Turn on or off debugging''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(options.split())
        except SystemExit:
            return
        self.sos_kernel._debug_mode = args.status == 'on'
        if self.sos_kernel._debug_mode:
            self.sos_kernel.warn(remaining_code)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Dict_Magic(SoS_Magic):
    name = 'dict'

    def __init__(self, kernel):
        super(Dict_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%dict',
                                         description='Inspect or reset SoS dictionary')
        parser.add_argument('vars', nargs='*')
        parser.add_argument('-k', '--keys', action='store_true',
                            help='Return only keys')
        parser.add_argument('-r', '--reset', action='store_true',
                            help='Rest SoS dictionary (clear all user variables)')
        parser.add_argument('-a', '--all', action='store_true',
                            help='Return all variales, including system functions and variables')
        parser.add_argument('-d', '--del', nargs='+', metavar='VAR', dest='__del__',
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
            if not x in env.sos_dict:
                self.sos_kernel.warn(
                    'Unrecognized sosdict option or variable name {}'.format(x))
                return

        if args.reset:
            self.sos_kernel._reset_dict()
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
                self.sos_kernel.send_result({x for x in env.sos_dict._dict.keys(
                ) if not x.startswith('__')} - self.sos_kernel.original_keys)
        else:
            if args.all:
                self.sos_kernel.send_result(env.sos_dict._dict)
            elif args.vars:
                self.sos_kernel.send_result(
                    {x: y for x, y in env.sos_dict._dict.items() if x in args.vars})
            else:
                self.sos_kernel.send_result({x: y for x, y in env.sos_dict._dict.items() if
                                         x not in self.sos_kernel.original_keys and not x.startswith('__')})

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        # %dict should be the last magic
        options, remaining_code = self.get_magic_and_code(code, False)
        self.handle_magic_dict(options)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Expand_Magic(SoS_Magic):
    name = 'expand'

    def __init__(self, kernel):
        super(Expand_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%expand',
                                         description='''Expand the script in the current cell with default ({}) or
                specified sigil.''')
        parser.add_argument('sigil', nargs='?', help='''Sigil to be used to interpolated the
            texts. It can be quoted, or be specified as two options.''')
        parser.add_argument('right_sigil', nargs='?', help='''Right sigil if the sigil is
            specified as two pieces.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        lines = code.splitlines()
        options = lines[0]
        parser = self.get_parser()
        try:
            args = parser.parse_args(options.split()[1:])
        except SystemExit:
            return
        if self.sos_kernel.kernel.lower() == 'sos':
            self.sos_kernel.warn(
                'Use of %expand magic in SoS cells is deprecated.')
        if args.sigil in ('None', None):
            sigil = None
        if args.right_sigil is not None:
            sigil = f'{args.sigil} {args.right_sigil}'
        # now we need to expand the text, but separate the SoS magics first
        lines = lines[1:]
        start_line: int = 0
        for idx, line in enumerate(lines):
            if line.strip() and not any(line.startswith(f'%{x} ') for x in SoS_Magics.names) and not line.startswith('!'):
                start_line = idx
                break
        text = '\n'.join(lines[start_line:])
        if sigil is not None and sigil != '{ }':
            from sos.parser import replace_sigil
            text = replace_sigil(text, sigil)
        try:
            interpolated = interpolate(text, local_dict=env.sos_dict._dict)
            remaining_code = '\n'.join(
                lines[:start_line] + [interpolated]) + '\n'
            # self.sos_kernel.options will be set to inflence the execution of remaing_code
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(e)
            return


class Get_Magic(SoS_Magic):
    name = 'get'

    def __init__(self, kernel):
        super(Get_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%get',
                                         description='''Get specified variables from another kernel, which is
                by default the SoS kernel.''')
        parser.add_argument('--from', dest='__from__',
                            help='''Name of kernel from which the variables will be obtained.
                Default to the SoS kernel.''')
        parser.add_argument('vars', nargs='*',
                            help='''Names of SoS variables''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(options.split())
            except SystemExit:
                return
        except Exception as e:
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        self.sos_kernel.get_vars_from(args.vars, args.__from__, explicit=True)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Matplotlib_Magic(SoS_Magic):
    name = 'matplotlib'

    def __init__(self, kernel):
        super(Matplotlib_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%matplotlib',
                                         description='''Set matplotlib parser type''')
        parser.add_argument('gui', choices=['agg', 'gtk', 'gtk3', 'inline', 'ipympl', 'nbagg',
                                            'notebook', 'osx', 'pdf', 'ps', 'qt', 'qt4', 'qt5', 'svg', 'tk', 'widget', 'wx'],
                            nargs='?',
                            help='''Name of the matplotlib backend to use (‘agg’, ‘gtk’, ‘gtk3’,''')
        parser.add_argument('-l', '--list', action='store_true',
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
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                      {'name': 'stdout', 'text': 'Available matplotlib backends: {}'.format(
                                          ['agg', 'gtk', 'gtk3', 'inline', 'ipympl', 'nbagg', 'notebook',
                                           'osx', 'pdf', 'ps', 'qt', 'qt4', 'qt5', 'svg', 'tk', 'widget', 'wx'])})
            return
        try:
            _, backend = self.sos_kernel.shell.enable_matplotlib(args.gui)
            if not args.gui or args.gui == 'auto':
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                          {'name': 'stdout',
                                           'text': f'Using matplotlib backend {backend}'})
        except Exception as e:
            self.sos_kernel.warn(
                'Failed to set matplotlib backnd {}: {}'.format(options, e))
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Paste_Magic(SoS_Magic):
    name = 'paste'

    def __init__(self, kernel):
        super(Paste_Magic, self).__init__(kernel)

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        if self.sos_kernel._meta.get('batch_mode', False):
            return
        options, remaining_code = self.get_magic_and_code(code, True)
        try:
            old_options = self.sos_kernel.options
            self.sos_kernel.options = options + ' ' + self.sos_kernel.options
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
                env.logger.warn(
                    f'Failed to get text from the clipboard: {e}')
                return
            #
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                      {'name': 'stdout', 'text': code.strip() + '\n## -- End pasted text --\n'})
            return self.sos_kernel._do_execute(code, silent, store_history, user_expressions, allow_stdin)
        finally:
            self.sos_kernel.options = old_options


class Preview_Magic(SoS_Magic):
    name = 'preview'

    def __init__(self, kernel):
        super(Preview_Magic, self).__init__(kernel)
        self.previewers = None

    def preview_var(self, item, style=None):
        if item in env.sos_dict:
            obj = env.sos_dict[item]
        else:
            obj = SoS_eval(item)
        # get the basic information of object
        txt = type(obj).__name__
        # we could potentially check the shape of data frame and matrix
        # but then we will need to import the numpy and pandas libraries
        if hasattr(obj, 'shape') and getattr(obj, 'shape') is not None:
            txt += f' of shape {getattr(obj, "shape")}'
        elif isinstance(obj, Sized):
            txt += f' of length {obj.__len__()}'
        if isinstance(obj, ModuleType):
            return txt, ({'text/plain': pydoc.render_doc(obj, title='SoS Documentation: %s')}, {})
        elif hasattr(obj, 'to_html') and getattr(obj, 'to_html') is not None:
            try:
                from sos.visualize import Visualizer
                result = Visualizer(self, style).preview(obj)
                if isinstance(result, (list, tuple)) and len(result) == 2:
                    return txt, result
                elif isinstance(result, dict):
                    return txt, (result, {})
                elif result is None:
                    return txt, None
                else:
                    raise ValueError(
                        f'Unrecognized return value from visualizer: {short_repr(result)}.')
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
                self.sos_kernel.send_frontend_msg('display_data',
                                              {
                                                  'metadata': {},
                                                  'data': {'text/html': HTML(
                                                      f'<div class="sos_hint">{hint_line}</div>').data}
                                              })
            if result:
                self.sos_kernel.send_frontend_msg('stream',
                                              {'name': 'stdout',
                                                  'text': result},
                                              )
        elif isinstance(result, dict):
            self.sos_kernel.send_frontend_msg('display_data',
                                          {'data': result, 'metadata': {}},
                                          )
        elif isinstance(result, (list, tuple)) and len(result) == 2:
            self.sos_kernel.send_frontend_msg('display_data',
                                          {'data': result[0],
                                           'metadata': result[1]},
                                          )
        else:
            self.sos_kernel.send_frontend_msg('stream',
                                          dict(
                                              name='stderr', text=f'Unrecognized preview content: {result}'),
                                          )

    def preview_file(self, filename, style=None):
        if not os.path.isfile(filename):
            self.sos_kernel.warn('\n> ' + filename + ' does not exist')
            return
        self.sos_kernel.send_frontend_msg('display_data',
                                      {'metadata': {},
                                       'data': {
                                          'text/plain': f'\n> {filename} ({pretty_size(os.path.getsize(filename))}):',
                                          'text/html': HTML(
                                              f'<div class="sos_hint">> {filename} ({pretty_size(os.path.getsize(filename))}):</div>').data,
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
                            self.sos_kernel.send_frontend_msg('stream',
                                                          dict(name='stderr',
                                                               text=f'Failed to load previewer {y}: {e}'),
                                                          )
                            continue
                        break
                except Exception as e:
                    self.sos_kernel.send_frontend_msg('stream', {
                        'name': 'stderr',
                        'text': str(e)}
                        )
                    continue
        #
        # if no previewer can be found
        if previewer_func is None:
            return
        try:
            result = previewer_func(filename, self.sos_kernel, style)
            self.show_preview_result(result)
        except Exception as e:
            if self.sos_kernel._debug_mode:
                self.sos_kernel.send_frontend_msg('stream',
                                              dict(
                                                  name='stderr', text=f'Failed to preview {filename}: {e}'),
                                              )

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%preview',
                                         description='''Preview files, sos variables, or expressions in the
                side panel, or notebook if side panel is not opened, unless
                options --panel or --notebook is specified.''')
        parser.add_argument('items', nargs='*',
                            help='''Filename, variable name, or expression. Wildcard characters
                such as '*' and '?' are allowed for filenames.''')
        parser.add_argument('-k', '--kernel',
                            help='''kernel in which variables will be previewed. By default
            the variable will be previewed in the current kernel of the cell.''')
        parser.add_argument('-w', '--workflow', action='store_true',
                            help='''Preview notebook workflow''')
        parser.add_argument('-o', '--keep-output', action='store_true',
                            help='''Do not clear the output of the side panel.''')
        # this option is currently hidden
        parser.add_argument('-s', '--style', choices=['table', 'scatterplot', 'png'],
                            help='''Option for preview file or variable, which by default is "table"
            for Pandas DataFrame. The %%preview magic also accepts arbitrary additional
            keyword arguments, which would be interpreted by individual style. Passing
            '-h' with '--style' would display the usage information of particular
            style.''')
        parser.add_argument('-r', '--host', dest='host', metavar='HOST',
                            help='''Preview files on specified remote host, which should
            be one of the hosts defined in sos configuration files.''')
        loc = parser.add_mutually_exclusive_group()
        loc.add_argument('-p', '--panel', action='store_true',
                         help='''Preview in side panel even if the panel is currently closed''')
        loc.add_argument('-n', '--notebook', action='store_true',
                         help='''Preview in the main notebook.''')
        parser.add_argument('-c', '--config', help='''A configuration file with host
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
                    self.sos_kernel.send_frontend_msg('display_data',
                                                  {'metadata': {},
                                                   'data': {'text/plain': '>>> ' + item + ':\n',
                                                            'text/html': HTML(
                                                                f'<div class="sos_hint">> {item}: directory<br>{len(files)}  file{"s" if len(files)>1 else ""}<br>{len(dirs)}  subdirector{"y" if len(dirs)<=1 else "ies"}</div>').data
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
        use_sos = kernel in ('sos', 'SoS') or (
            kernel is None and self.sos_kernel.kernel == 'SoS')
        orig_kernel = self.sos_kernel.kernel
        if kernel is not None and self.sos_kernel.kernel != self.sos_kernel.subkernels.find(kernel).name:
            self.sos_kernel.switch_kernel(kernel)
        if self.sos_kernel._meta['use_panel']:
            self.sos_kernel.send_frontend_msg(
                'preview-kernel', self.sos_kernel.kernel)
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
                        self.sos_kernel.send_frontend_msg('display_data',
                                                      {'metadata': {},
                                                       'data': {'text/plain': '>>> ' + item + ':\n',
                                                                'text/html': HTML(
                                                                    f'<div class="sos_hint">> {item}: {obj_desc}</div>').data
                                                                }
                                                       })
                        self.show_preview_result(preview)
                        continue
                    # not sos
                    if self.sos_kernel.kernel in self.sos_kernel.supported_languages:
                        lan = self.sos_kernel.supported_languages[self.sos_kernel.kernel]
                        kinfo = self.sos_kernel.subkernels.find(self.sos_kernel.kernel)
                        lan_obj = lan(self.sos_kernel, kinfo.kernel)
                        if hasattr(lan_obj, 'preview') and callable(lan_obj.preview):
                            try:
                                obj_desc, preview = lan_obj.preview(item)
                                self.sos_kernel.send_frontend_msg('display_data',
                                          {'metadata': {},
                                           'data': {'text/plain': '>>> ' + item + ':\n',
                                                    'text/html': HTML(
                                                        f'<div class="sos_hint">> {item}: {obj_desc}</div>').data
                                                    }
                                           })
                                self.show_preview_result(preview)
                            except Exception as e:
                                self.warn(f'Failed to preview {item}: {e}')
                            continue
                    # if no preview function defined
                    # evaluate the expression itself
                    responses = self.sos_kernel.get_response(
                        item, ['stream', 'display_data', 'execution_result', 'error'])
                    if not self.sos_kernel._debug_mode:
                        # if the variable or expression is invalid, do not do anything
                        responses = [
                            x for x in responses if x[0] != 'error']
                    if responses:
                        self.sos_kernel.send_frontend_msg('display_data',
                                                      {'metadata': {},
                                                       'data': {'text/plain': '>>> ' + item + ':\n',
                                                                'text/html': HTML(
                                                                    f'<div class="sos_hint">> {item}:</div>').data
                                                                }
                                                       })
                        for response in responses:
                            # self.sos_kernel.warn(f'{response[0]} {response[1]}' )
                            self.sos_kernel.send_frontend_msg(
                                response[0], response[1])
                    else:
                        raise ValueError(
                            f'Cannot preview expresison {item}')
                except Exception as e:
                    if not handled[idx]:
                        self.sos_kernel.send_frontend_msg('stream',
                                                      dict(name='stderr',
                                                           text='> Failed to preview file or expression {}{}'.format(
                                                               item, f': {e}' if self.sos_kernel._debug_mode else ''))
                                                      )
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
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        finally:
            self.sos_kernel._no_auto_preview = False
            # preview workflow
            if args.workflow:
                import random
                ta_id = 'preview_wf_{}'.format(random.randint(1, 1000000))
                content = {
                    'data': {
                        'text/plain': self.sos_kernel._meta['workflow'],
                        'text/html': HTML(
                            f'<textarea id="{ta_id}">{self.sos_kernel._meta["workflow"]}</textarea>').data
                    },
                    'metadata': {}
                }
                self.sos_kernel.send_frontend_msg('display_data', content)
                self.sos_kernel.send_frontend_msg('highlight-workflow', ta_id)
            if not args.items:
                return
            if args.host:
                title = f'%preview {" ".join(args.items)} -r {args.host}'
            else:
                title = f'%preview {" ".join(args.items)}'
            # reset preview panel
            if not self.sos_kernel._meta['use_panel']:
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                          {
                                              'metadata': {},
                                              'data': {'text/html': HTML(f'<div class="sos_hint">{title}</div>').data}
                                          })
            else:
                # clear the page
                self.sos_kernel.send_frontend_msg(
                    'display_data', {})
            if args.host is None:
                self.handle_magic_preview(
                    args.items, args.kernel, style)
            elif args.workflow:
                self.sos_kernel.warn(
                    'Invalid option --kernel with -r (--host)')
            elif args.kernel:
                self.sos_kernel.warn(
                    'Invalid option --kernel with -r (--host)')
            else:
                if args.config:
                    from sos.utils import load_config_files
                    load_config_files(args.config)
                try:
                    rargs = ['sos', 'preview', '--html'] + options
                    rargs = [x for x in rargs if x not in (
                        '-n', '--notebook', '-p', '--panel')]
                    if self.sos_kernel._debug_mode:
                        self.sos_kernel.warn(f'Running "{" ".join(rargs)}"')
                    for msg in eval(subprocess.check_output(rargs)):
                        self.sos_kernel.send_frontend_msg(
                            msg[0], msg[1])
                except Exception as e:
                    self.sos_kernel.warn('Failed to preview {} on remote host {}{}'.format(
                        args.items, args.host, f': {e}' if self.sos_kernel._debug_mode else ''))


class Pull_Magic(SoS_Magic):
    name = 'pull'

    def __init__(self, kernel):
        super(Pull_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser('pull',
                                         description='''Pull files or directories from remote host to local host''')
        parser.add_argument('items', nargs='+', help='''Files or directories to be
            retrieved from remote host. The files should be relative to local file
            system. The files to retrieve are determined by "path_map"
            determined by "paths" definitions of local and remote hosts.''')
        parser.add_argument('-f', '--from', dest='host',
                            help='''Remote host to which the files will be sent, which should
            be one of the hosts defined in sos configuration files.''')
        parser.add_argument('-c', '--config', help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.add_argument('-v', '--verbosity', type=int, choices=range(5), default=2,
                            help='''Output error (0), warning (1), info (2), debug (3) and trace (4)
                information to standard output (default to 2).''')
        parser.error = self._parse_error
        return parser

    def handle_magic_pull(self, args):
        from sos.hosts import Host
        if args.config:
            from sos.utils import load_config_files
            load_config_files(args.config)
        try:
            host = Host(args.host)
            #
            received = host.receive_from_host(args.items)
            #
            msg = '{} item{} received from {}:<br>{}'.format(len(received),
                                                             ' is' if len(
                                                                 received) <= 1 else 's are', args.host,
                                                             '<br>'.join([f'{x} <= {received[x]}' for x in
                                                                          sorted(received.keys())]))
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                      {
                                          'metadata': {},
                                          'data': {'text/html': HTML(f'<div class="sos_hint">{msg}</div>').data}
                                      })
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to retrieve {", ".join(args.items)}: {e}')

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(options.split())
            except SystemExit:
                return
        except Exception as e:
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        self.handle_magic_pull(args)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Push_Magic(SoS_Magic):
    name = 'push'

    def __init__(self, kernel):
        super(Push_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser('push',
                                         description='''Push local files or directory to a remote host''')
        parser.add_argument('items', nargs='+', help='''Files or directories to be sent
            to remote host. The location of remote files are determined by "path_map"
            determined by "paths" definitions of local and remote hosts.''')
        parser.add_argument('-t', '--to', dest='host',
                            help='''Remote host to which the files will be sent. SoS will list all
            configured queues if no such key is defined''')
        parser.add_argument('-c', '--config', help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.add_argument('-v', '--verbosity', type=int, choices=range(5), default=2,
                            help='''Output error (0), warning (1), info (2), debug (3) and trace (4)
                information to standard output (default to 2).''')
        parser.error = self._parse_error
        return parser

    def handle_magic_push(self, args):
        from sos.hosts import Host
        if args.config:
            from sos.utils import load_config_files
            load_config_files(args.config)
        try:
            host = Host(args.host)
            #
            sent = host.send_to_host(args.items)
            #
            msg = '{} item{} sent to {}:<br>{}'.format(len(sent),
                                                       ' is' if len(
                                                           sent) <= 1 else 's are', args.host,
                                                       '<br>'.join([f'{x} => {sent[x]}' for x in sorted(sent.keys())]))
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                      {
                                          'metadata': {},
                                          'data': {'text/html': HTML(f'<div class="sos_hint">{msg}</div>').data}
                                      })
        except Exception as e:
            self.sos_kernel.warn(f'Failed to send {", ".join(args.items)}: {e}')

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(options.split())
            except SystemExit:
                return
        except Exception as e:
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        self.handle_magic_push(args)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Put_Magic(SoS_Magic):
    name = 'put'

    def __init__(self, kernel):
        super(Put_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%put',
                                         description='''Put specified variables in the subkernel to another
            kernel, which is by default the SoS kernel.''')
        parser.add_argument('--to', dest='__to__',
                            help='''Name of kernel from which the variables will be obtained.
                Default to the SoS kernel.''')
        parser.add_argument('vars', nargs='*',
                            help='''Names of SoS variables''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        try:
            parser = self.get_parser()
            try:
                args = parser.parse_args(options.split())
            except SystemExit:
                return
        except Exception as e:
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        self.sos_kernel.put_vars_to(args.vars, args.__to__, explicit=True)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Render_Magic(SoS_Magic):
    name = 'render'

    def __init__(self, kernel):
        super(Render_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%render',
                                         description='''Treat the output of a SoS cell as another format, default to markdown.''')
        parser.add_argument('msg_type', default='stdout', choices=['stdout', 'text'], nargs='?',
                            help='''Message type to capture, default to standard output. In terms of Jupyter message
                        types, "stdout" refers to "stream" message with "stdout" type, and "text" refers to
                        "display_data" message with "text/plain" type.''')
        parser.add_argument('--as', dest='as_type', default='Markdown', nargs='?',
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
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        finally:
            content = ''
            if args.msg_type == 'stdout':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'stream' and msg[1]['name'] == 'stdout':
                        content += msg[1]['text']
            elif args.msg_type == 'text':
                for msg in self.sos_kernel._meta['capture_result']:
                    if msg[0] == 'display_data' and 'data' in msg[1] and 'text/plain' in msg[1]['data']:
                        content += msg[1]['data']['text/plain']
            try:
                if content:
                    format_dict, md_dict = self.sos_kernel.format_obj(
                        self.sos_kernel.render_result(content))
                    self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                              {'metadata': md_dict,
                                               'data': format_dict
                                               })
            finally:
                self.sos_kernel._meta['capture_result'] = None
                self.sos_kernel._meta['render_result'] = False


class Rerun_Magic(SoS_Magic):
    name = 'rerun'

    def __init__(self, kernel):
        super(Rerun_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%rerun',
                                         description='''Re-execute the last executed code, most likely with
            different command line options''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, True)
        old_options = self.sos_kernel.options
        self.sos_kernel.options = options + ' ' + self.sos_kernel.options
        try:
            self.sos_kernel._meta['workflow_mode'] = True
            old_dict = env.sos_dict
            self.sos_kernel._reset_dict()
            if not self.sos_kernel.last_executed_code:
                self.sos_kernel.warn('No saved script')
                self.sos_kernel.last_executed_code = ''
            return self.sos_kernel._do_execute(self.sos_kernel.last_executed_code, silent, store_history, user_expressions, allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(f'Failed to execute workflow: {e}')
            raise
        finally:
            old_dict.quick_update(env.sos_dict._dict)
            env.sos_dict = old_dict
            self.sos_kernel._meta['workflow_mode'] = False
            self.sos_kernel.options = old_options


class Revisions_Magic(SoS_Magic):
    name = 'revisions'

    def __init__(self, kernel):
        super(Revisions_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%revision',
                                         description='''Revision history of the document, parsed from the log
            message of the notebook if it is kept in a git repository. Additional parameters to "git log" command
            (e.g. -n 5 --since --after) could be specified to limit the revisions to display.''')
        parser.add_argument('-s', '--source', nargs='?', default='',
                            help='''Source URL to to create links for revisions.
            SoS automatically parse source URL of the origin and provides variables "repo" for complete origin
            URL without trailing ".git" (e.g. https://github.com/vatlab/sos-notebook), "path" for complete
            path name (e.g. src/document/doc.ipynb), "filename" for only the name of the "path", and "revision"
            for revisions. Because sos interpolates command line by default, variables in URL template should be
            included with double braceses (e.g. --source {{repo}}/blob/{{revision}}/{{path}})). If this option is
            provided without value and the document is hosted on github, a default template will be provided.''')
        parser.add_argument('-l', '--links', nargs='+', help='''Name and URL or additional links for related
            files (e.g. --links report URL_to_repo ) with URL interpolated as option --source.''')
        parser.error = self._parse_error
        return parser

    def handle_magic_revisions(self, args, unknown_args):
        filename = self.sos_kernel._meta['notebook_name'] + '.ipynb'
        path = self.sos_kernel._meta['notebook_path']
        revisions = subprocess.check_output(['git', 'log'] + unknown_args + ['--date=short', '--pretty=%H!%cN!%cd!%s',
                                                                             '--', filename]).decode().splitlines()
        if not revisions:
            return
        # args.source is None for --source without option
        if args.source != '' or args.links:
            # need to determine origin etc for interpolation
            try:
                origin = subprocess.check_output(
                    ['git', 'ls-remote', '--get-url', 'origin']).decode().strip()
                repo = origin[:-4] if origin.endswith('.git') else origin
            except Exception as e:
                repo = ''
                if self.sos_kernel._debug_mode:
                    self.sos_kernel.warn(f'Failed to get repo URL: {e}')
            if args.source is None:
                if 'github.com' in repo:
                    args.source = '{repo}/blob/{revision}/{path}'
                    if self.sos_kernel._debug_mode:
                        self.sos_kernel.warn(
                            f"source is set to {args.source} with repo={repo}")
                else:
                    args.source = ''
                    self.sos_kernel.warn(
                        f'A default source URL is unavailable for repository {repo}')
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
                URL = interpolate(args.source, {'revision': revision, 'repo': repo,
                                                'filename': filename, 'path': path})
                fields[0] = f'<a target="_blank" href="{URL}">{fields[0]}</a>'
            links = []
            if args.links:
                for i in range(len(args.links) // 2):
                    name = args.links[2 * i]
                    if len(args.links) == 2 * i + 1:
                        continue
                    URL = interpolate(args.links[2 * i + 1],
                                      {'revision': revision, 'repo': repo, 'filename': filename, 'path': path})
                    links.append(f'<a target="_blank" href="{URL}">{name}</a>')
            if links:
                fields[0] += ' (' + ', '.join(links) + ')'
            text += '<tr>' + \
                '\n'.join(f'<td>{x}</td>' for x in fields) + '</tr>'
        text += '</table>'
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                           {
                               'metadata': {},
                               'data': {'text/html': HTML(text).data}
                           })

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, True)
        parser = self.get_parser()
        try:
            args, unknown_args = parser.parse_known_args(
                shlex.split(options))
        except SystemExit:
            return
        try:
            self.handle_magic_revisions(args, unknown_args)
        except Exception as e:
            self.sos_kernel.warn(f'Failed to retrieve revisions of notebook: {e}')
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Run_Magic(SoS_Magic):
    name = 'run'

    def __init__(self, kernel):
        super(Run_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%run',
                                         description='''Execute the current cell with specified command line
            arguments. Arguments set by magic %set will be appended at the
            end of command line''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):

        # there can be multiple %run magic, but there should not be any other magics
        run_code = code
        run_options = []
        while True:
            if self.pattern.match(run_code):
                options, run_code = self.get_magic_and_code(
                    run_code, False)
                run_options.append(options)
            else:
                break
        # if there are more magics after %run, they will be ignored so a warning
        # is needed.
        if run_code.lstrip().startswith('%') and not any(run_code.lstrip().startswith(x) for x in ('%include', '%from')):
            self.sos_kernel.warn(
                f'Magic {run_code.split()[0]} after magic %run will be ignored.')

        if not any(SOS_SECTION_HEADER.match(line) for line in run_code.splitlines()):
            run_code = '[default]\n' + run_code
        # now we need to run the code multiple times with each option
        for options in run_options:
            old_options = self.sos_kernel.options
            self.sos_kernel.options = options + ' ' + self.sos_kernel.options
            try:
                # %run is executed in its own namespace
                old_dict = env.sos_dict
                self.sos_kernel._reset_dict()
                self.sos_kernel._meta['workflow_mode'] = True
                if self.sos_kernel._debug_mode:
                    self.sos_kernel.warn(f'Executing\n{run_code}')
                if self.sos_kernel.kernel != 'SoS':
                    self.sos_kernel.switch_kernel('SoS')
                ret = self.sos_kernel._do_execute(run_code, silent, store_history, user_expressions,
                                              allow_stdin)
            except Exception as e:
                self.sos_kernel.warn(f'Failed to execute workflow: {e}')
                raise
            finally:
                old_dict.quick_update(env.sos_dict._dict)
                env.sos_dict = old_dict
                self.sos_kernel._meta['workflow_mode'] = False
                self.sos_kernel.options = old_options
        return ret



class Sandbox_Magic(SoS_Magic):
    name = 'sandbox'

    def __init__(self, kernel):
        super(Sandbox_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%sandbox',
                                         description='''Execute content of a cell in a temporary directory
                with fresh dictionary (by default).''')
        parser.add_argument('-d', '--dir',
                            help='''Execute workflow in specified directory. The directory
                will be created if does not exist, and will not be removed
                after the completion. ''')
        parser.add_argument('-k', '--keep-dict', action='store_true',
                            help='''Keep current sos dictionary.''')
        parser.add_argument('-e', '--expect-error', action='store_true',
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
                self.sos_kernel._reset_dict()
            ret = self.sos_kernel._do_execute(
                remaining_code, silent, store_history, user_expressions, allow_stdin)
            if args.expect_error and ret['status'] == 'error':
                # self.sos_kernel.warn('\nSandbox execution failed.')
                return {'status': 'ok',
                        'payload': [], 'user_expressions': {},
                        'execution_count': self.sos_kernel._execution_count}
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
        parser = argparse.ArgumentParser(prog='%save',
                                         description='''Save the content of the cell (after the magic itself) to specified file''')
        parser.add_argument('filename',
                            help='''Filename of saved report or script.''')
        parser.add_argument('-f', '--force', action='store_true',
                            help='''If destination file already exists, overwrite it.''')
        parser.add_argument('-a', '--append', action='store_true',
                            help='''If destination file already exists, append to it.''')
        parser.add_argument('-x', '--set-executable', dest="setx", action='store_true',
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
                    f'Cannot overwrite existing output file {filename}')

            with open(filename, 'a' if args.append else 'w') as script:
                script.write(
                    '\n'.join(remaining_code.splitlines()).rstrip() + '\n')
            if args.setx:
                import stat
                os.chmod(filename, os.stat(
                    filename).st_mode | stat.S_IEXEC)

            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                      {'metadata': {},
                                       'data': {
                                          'text/plain': f'Cell content saved to {filename}\n',
                                          'text/html': HTML(
                                              f'<div class="sos_hint">Cell content saved to <a href="{filename}" target="_blank">{filename}</a></div>').data
                                      }
                                      })
            return
        except Exception as e:
            self.sos_kernel.warn(f'Failed to save cell: {e}')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }


class SessionInfo_Magic(SoS_Magic):
    name = 'sessioninfo'

    def __init__(self, kernel):
        super(SessionInfo_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%sessioninfo',
                                         description='''List the session info of all subkernels, and information
            stored in variable sessioninfo''')
        parser.error = self._parse_error
        return parser

    def handle_sessioninfo(self):
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
                result[kernel] = [
                    ('Kernel', kinfo.kernel),
                    ('Language', kinfo.language)
                ]
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
                            self.sos_kernel.warn(f'Unrecognized session info: {sinfo}')
                    except Exception as e:
                        self.sos_kernel.warn(
                            f'Failed to obtain sessioninfo of kernel {kernel}: {e}')
        finally:
            self.sos_kernel.switch_kernel(cur_kernel)
        #
        if 'sessioninfo' in env.sos_dict:
            result.update(env.sos_dict['sessioninfo'])
        #
        res = ''
        for key, items in result.items():
            res += f'<p class="session_section">{key}</p>\n'
            res += '<table class="session_info">\n'
            for item in items:
                res += '<tr>\n'
                if isinstance(item, str):
                    res += f'<td colspan="2"><pre>{item}</pre></td>\n'
                elif len(item) == 1:
                    res += f'<td colspan="2"><pre>{item[0]}</pre></td>\n'
                elif len(item) == 2:
                    res += f'<th>{item[0]}</th><td><pre>{item[1]}</pre></td>\n'
                else:
                    self.sos_kernel.warn(
                        f'Invalid session info item of type {item.__class__.__name__}: {short_repr(item)}')
                res += '</tr>\n'
            res += '</table>\n'
        self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                           {'metadata': {},
                            'data': {'text/html': HTML(res).data}})

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            parser.parse_known_args(shlex.split(options))
        except SystemExit:
            return
        self.handle_sessioninfo()
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Set_Magic(SoS_Magic):
    name = 'set'

    def __init__(self, kernel):
        super(Set_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%set',
                                         description='''Set persistent command line options for SoS runs.''')
        parser.error = self._parse_error
        return parser

    def handle_magic_set(self, options):
        if options.strip():
            # self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
            #    {'name': 'stdout', 'text': 'sos options set to "{}"\n'.format(options)})
            if not options.strip().startswith('-'):
                self.sos_kernel.warn(
                    f'Magic %set cannot set positional argument, {options} provided.\n')
            else:
                self.sos_kernel.options = options.strip()
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                          dict(name='stdout', text=f'Set sos options to "{self.sos_kernel.options}"\n'))
        else:
            if self.sos_kernel.options:
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                          dict(name='stdout', text=f'Reset sos options from "{self.sos_kernel.options}" to ""\n'))
                self.sos_kernel.options = ''
            else:
                self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'stream',
                                          {'name': 'stdout',
                                           'text': 'Usage: set persistent sos command line options such as "-v 3" (debug output)\n'})

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        self.handle_magic_set(options)
        # self.sos_kernel.options will be set to inflence the execution of remaing_code
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Shutdown_Magic(SoS_Magic):
    name = 'shutdown'

    def __init__(self, kernel):
        super(Shutdown_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%shutdown',
                                         description='''Shutdown or restart specified subkernel''')
        parser.add_argument('kernel', nargs='?',
                            help='''Name of the kernel to be restarted, default to the
            current running kernel.''')
        parser.add_argument('-r', '--restart', action='store_true',
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
        self.shutdown_kernel(
            args.kernel if args.kernel else self.sos_kernel, args.restart)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class SoSRun_Magic(SoS_Magic):
    name = 'sosrun'

    def __init__(self, kernel):
        super(SoSRun_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%sosrun',
                                         description='''Execute the entire notebook with steps consisting of SoS
            cells (cells with SoS kernel) with section header, with specified command
            line arguments. Arguments set by magic %set will be appended at the
            end of command line''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        old_options = self.sos_kernel.options
        self.sos_kernel.options = options + ' ' + self.sos_kernel.options
        try:
            if self.sos_kernel.kernel != 'SoS':
                self.sos_kernel.switch_kernel('SoS')
            # %run is executed in its own namespace
            old_dict = env.sos_dict
            self.sos_kernel._reset_dict()
            self.sos_kernel._meta['workflow_mode'] = True
            # self.sos_kernel.send_frontend_msg('preview-workflow', self.sos_kernel._meta['workflow'])
            if not self.sos_kernel._meta['workflow']:
                self.sos_kernel.warn(
                    'Nothing to execute (notebook workflow is empty).')
            else:
                self.sos_kernel._do_execute(self.sos_kernel._meta['workflow'], silent,
                                        store_history, user_expressions, allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(f'Failed to execute workflow: {e}')
            raise
        finally:
            old_dict.quick_update(env.sos_dict._dict)
            env.sos_dict = old_dict
            self.sos_kernel._meta['workflow_mode'] = False
            self.sos_kernel.options = old_options
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class SoSSave_Magic(SoS_Magic):
    name = 'sossave'

    def __init__(self, kernel):
        super(SoSSave_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%sossave',
                                         description='''Save the jupyter notebook as workflow (consisting of all sos
            steps defined in cells starting with section header) or a HTML report to
            specified file.''')
        parser.add_argument('filename', nargs='?',
                            help='''Filename of saved report or script. Default to notebookname with file
            extension determined by option --to.''')
        parser.add_argument('-t', '--to', dest='__to__', choices=['sos', 'html'],
                            help='''Destination format, default to sos.''')
        parser.add_argument('-c', '--commit', action='store_true',
                            help='''Commit the saved file to git directory using command
            git commit FILE''')
        parser.add_argument('-a', '--all', action='store_true',
                            help='''The --all option for sos convert script.ipynb script.sos, which
            saves all cells and their metadata to a .sos file, that contains all input
            information of the notebook but might not be executable in batch mode.''')
        parser.add_argument('-m', '--message',
                            help='''Message for git commit. Default to "save FILENAME"''')
        parser.add_argument('-p', '--push', action='store_true',
                            help='''Push the commit with command "git push"''')
        parser.add_argument('-f', '--force', action='store_true',
                            help='''If destination file already exists, overwrite it.''')
        parser.add_argument('-x', '--set-executable', dest="setx", action='store_true',
                            help='''Set `executable` permission to saved script.''')
        parser.add_argument('--template', default='default-sos-template',
                            help='''Template to generate HTML output. The default template is a
            template defined by configuration key default-sos-template, or
            sos-report if such a key does not exist.''')
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
                            f'%sossave to an .html file in {args.__to__} format')
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
                if not args.all:
                    with open(filename, 'w') as script:
                        script.write(self.sos_kernel._meta['workflow'])
                else:
                    # convert to sos report
                    from .converter import notebook_to_script
                    arg = argparse.Namespace()
                    arg.execute = False
                    arg.all = True
                    notebook_to_script(
                        self.sos_kernel._meta['notebook_name'] + '.ipynb', filename, args=arg, unknown_args=[])
                if args.setx:
                    import stat
                    os.chmod(filename, os.stat(
                        filename).st_mode | stat.S_IEXEC)
            else:
                # convert to sos report
                from .converter import notebook_to_html
                arg = argparse.Namespace()
                if args.template == 'default-sos-template':
                    from sos.utils import load_config_files
                    cfg = load_config_files()
                    if 'default-sos-template' in cfg:
                        arg.template = cfg['default-sos-template']
                    else:
                        arg.template = 'sos-report'
                else:
                    arg.template = args.template
                arg.view = False
                arg.execute = False
                notebook_to_html(self.sos_kernel._meta['notebook_name'] + '.ipynb',
                                 filename, sargs=arg, unknown_args=[])

            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                      {'metadata': {},
                                       'data': {
                                          'text/plain': f'Workflow saved to {filename}\n',
                                          'text/html': HTML(
                                              f'<div class="sos_hint">Workflow saved to <a href="{filename}" target="_blank">{filename}</a></div>').data
                                      }
                                      })
            #
            if args.commit:
                self.run_shell_command({'git', 'commit', filename, '-m',
                                           args.message if args.message else f'save {filename}'})
            if args.push:
                self.run_shell_command(['git', 'push'])
            return
        except Exception as e:
            self.sos_kernel.warn(f'Failed to save workflow: {e}')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }


class TaskInfo_Magic(SoS_Magic):
    name = 'taskinfo'

    def __init__(self, kernel):
        super(TaskInfo_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%taskinfo',
                                         description='''Get information on specified task. By default
            sos would query against all running task queues but it would
            start a task queue and query status if option -q is specified.
            ''')
        parser.add_argument('task', help='ID of task')
        parser.add_argument('-q', '--queue',
                            help='''Task queue on which the task is executed.''')
        parser.add_argument('-c', '--config', help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(options.split())
        except SystemExit:
            return
        if args.config:
            from sos.utils import load_cfg_files
            load_cfg_files(args.config)
        self.sos_kernel.update_taskinfo(args.task, args.queue)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Tasks_Magic(SoS_Magic):
    name = 'tasks'

    def __init__(self, kernel):
        super(Tasks_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%tasks',
                                         description='''Show a list of tasks from specified queue''')
        parser.add_argument('tasks', nargs='*', help='ID of tasks')
        parser.add_argument('-s', '--status', nargs='*',
                            help='''Display tasks of specified status. Default to all.''')
        parser.add_argument('-q', '--queue',
                            help='''Task queue on which the tasks are retrived.''')
        parser.add_argument('--age', help='''Limit to tasks that is created more than
            (default) or within specified age. Value of this parameter can be in units
            s (second), m (minute), h (hour), or d (day, default), with optional
            prefix + for older (default) and - for younder than specified age.''')
        parser.add_argument('-c', '--config', help='''A configuration file with host
            definitions, in case the definitions are not defined in global or local
            sos config.yml files.''')
        parser.error = self._parse_error
        return parser

    def handle_tasks(self, tasks, queue='localhost', status=None, age=None):
        from sos.hosts import Host
        try:
            host = Host(queue)
        except Exception as e:
            self.sos_kernel.warn('Invalid task queu {}: {}'.format(queue, e))
            return
        # get all tasks
        for tid, tst, tdt in host._task_engine.monitor_tasks(tasks, status=status, age=age):
            self.sos_kernel.send_frontend_msg('task_status',
                {'cell_id': self.sos_kernel.cell_id,
                 'queue': queue,
                 'task_id': tid,
                 'status': tst})

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(options.split())
        except SystemExit:
            return
        if args.config:
            from sos.utils import load_cfg_files
            load_cfg_files(args.config)
        self.handle_tasks(
            args.tasks, args.queue if args.queue else 'localhost', args.status, args.age)
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


def header_to_toc(text, id):
    '''Convert a bunch of ## header to TOC'''
    toc = [f'<div class="toc" id="{id}">' if id else '<div class="toc">']
    lines = [x for x in text.splitlines() if x.strip()]
    if not lines:
        return ''
    top_level = min(x.split(' ')[0].count('#') for x in lines)
    level = top_level - 1
    for line in lines:
        header, text = line.split(' ', 1)
        # the header might have anchor link like <a id="videos"></a>
        matched = re.match('.*(<a\s+id="(.*)">.*</a>).*', text)
        anchor = ''
        if matched:
            text = text.replace(matched.group(1), '')
            anchor = matched.group(2)
        # remove image
        matched = re.match('.*(<img .*>).*', text)
        if matched:
            text = text.replace(matched.group(1), '')
        if not anchor:
            anchor = re.sub('[^ a-zA-Z0-9]', '',
                            text).strip().replace(' ', '-')
        # handle ` ` in header
        text = re.sub('`(.*?)`', '<code>\\1</code>', text)
        line_level = header.count('#')
        if line_level > level:
            # level          2
            # line_leval     4
            # add level 3, 4
            for l in range(level + 1, line_level + 1):
                # increase level, new ui
                toc.append(f'<ul class="toc-item lev{l - top_level}">')
        elif line_level < level:
            # level          4
            # line_level     2
            # end level 4 and 3.
            for level in range(level - line_level):
                # end last one
                toc.append('</ul>')
        level = line_level
        toc.append(f'''<li><a href="#{anchor}">{text}</a></li>''')
    # if last level is 4, toplevel is 2 ...
    if level:
        for level in range(level - top_level):
            toc.append('</div>')
    return HTML('\n'.join(toc)).data


class Toc_Magic(SoS_Magic):
    name = 'toc'

    def __init__(self, kernel):
        super(Toc_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%toc',
                                         description='''Generate a table of content from the current notebook.''')
        loc = parser.add_mutually_exclusive_group()
        loc.add_argument('-p', '--panel', action='store_true',
                         help='''Show the TOC in side panel even if the panel is currently closed''')
        loc.add_argument('-n', '--notebook', action='store_true',
                         help='''Show the TOC in the main notebook.''')
        parser.add_argument(
            '--id', help='''Optional ID of the generated TOC.''')
        parser.error = self._parse_error
        return parser

    def apply(self, code, silent, store_history, user_expressions, allow_stdin):
        options, remaining_code = self.get_magic_and_code(code, False)
        parser = self.get_parser()
        try:
            args = parser.parse_args(shlex.split(options))
        except SystemExit:
            return
        if args.panel:
            self.sos_kernel._meta['use_panel'] = True
        elif args.notebook:
            self.sos_kernel._meta['use_panel'] = False
        if self.sos_kernel._meta['use_panel']:
            self.sos_kernel.send_frontend_msg('show_toc')
        else:
            self.sos_kernel.send_response(self.sos_kernel.iopub_socket, 'display_data',
                                      {'metadata': {},
                                       'data': {
                                          'text/html': header_to_toc(self.sos_kernel._meta['toc'], args.id)
                                      },
                                      })
        return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)


class Use_Magic(SoS_Magic):
    name = 'use'

    def __init__(self, kernel):
        super(Use_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%use',
                                         description='''Switch to an existing subkernel
            or start a new subkernel.''')
        parser.add_argument('name', nargs='?', default='',
                            help='''Displayed name of kernel to start (if no kernel with name is
            specified) or switch to (if a kernel with this name is already started).
            The name is usually a kernel name (e.g. %%use ir) or a language name
            (e.g. %%use R) in which case the language name will be used. One or
            more parameters --language or --kernel will need to be specified
            if a new name is used to start a separate instance of a kernel.''')
        parser.add_argument('-k', '--kernel',
                            help='''kernel name as displayed in the output of jupyter kernelspec
            list. Default to the default kernel of selected language (e.g. ir for
            language R.''')
        parser.add_argument('-l', '--language',
                            help='''Language extension that enables magics such as %%get and %%put
            for the kernel, which should be in the name of a registered language
            (e.g. R), or a specific language module in the format of
            package.module:class. SoS maitains a list of languages and kernels
            so this option is only needed for starting a new instance of a kernel.
            ''')
        parser.add_argument('-c', '--color',
                            help='''Background color of new or existing kernel, which overrides
            the default color of the language. A special value "default" can be
            used to reset color to default.''')
        parser.add_argument('-r', '--restart', action='store_true',
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
            return {'status': 'abort',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        if args.restart and args.name in elf.kernel.kernels:
            self.shutdown_kernel(args.name)
            self.sos_kernel.warn(f'{args.name} is shutdown')
        try:
            self.sos_kernel.switch_kernel(args.name, None, None, args.kernel,
                                      args.language, args.color)
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to switch to subkernel {args.name} (kernel {args.kernel}, language {args.language}): {e}')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }


class With_Magic(SoS_Magic):
    name = 'with'

    def __init__(self, kernel):
        super(With_Magic, self).__init__(kernel)

    def get_parser(self):
        parser = argparse.ArgumentParser(prog='%with',
                                         description='''Use specified subkernel to evaluate current
            cell, with optional input and output variables''')
        parser.add_argument('name', nargs='?', default='',
                            help='''Name of an existing kernel.''')
        parser.add_argument('-i', '--in', nargs='*', dest='in_vars',
                            help='Input variables (variables to get from SoS kernel)')
        parser.add_argument('-o', '--out', nargs='*', dest='out_vars',
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
            self.sos_kernel.warn(f'Invalid option "{options}": {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }

        original_kernel = self.sos_kernel.kernel
        try:
            self.sos_kernel.switch_kernel(args.name, args.in_vars, args.out_vars)
        except Exception as e:
            self.sos_kernel.warn(
                f'Failed to switch to subkernel {args.name}): {e}')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self.sos_kernel._execution_count,
                    }
        try:
            return self.sos_kernel._do_execute(remaining_code, silent, store_history, user_expressions, allow_stdin)
        finally:
            self.sos_kernel.switch_kernel(original_kernel)


class SoS_Magics(object):
    magics = [
        Command_Magic,
        Capture_Magic,
        Cd_Magic,
        Clear_Magic,
        ConnectInfo_Magic,
        Debug_Magic,
        Dict_Magic,
        Expand_Magic,
        Get_Magic,
        Matplotlib_Magic,
        Preview_Magic,
        Pull_Magic,
        Paste_Magic,
        Push_Magic,
        Put_Magic,
        Render_Magic,
        Rerun_Magic,
        Run_Magic,
        Revisions_Magic,
        Save_Magic,
        Set_Magic,
        SessionInfo_Magic,
        Shutdown_Magic,
        SoSRun_Magic,
        SoSSave_Magic,
        TaskInfo_Magic,
        Tasks_Magic,
        Toc_Magic,
        Sandbox_Magic,
        Use_Magic,
        With_Magic
    ]
    names = [x.name for x in magics if x.name != '!']

    def __init__(self, kernel=None):
        self._magics = {x.name: x(kernel) for x in self.magics}

    def get(self, name):
        return self._magics[name]

    def values(self):
        return self._magics.values()
