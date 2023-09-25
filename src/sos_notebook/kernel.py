#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.
import asyncio
import contextlib
import inspect
import logging
import os
import pprint
import subprocess
import sys
import threading
import time
from collections import defaultdict
from textwrap import dedent

import comm
import pandas as pd
import pkg_resources
from ipykernel._version import version_info as ipykernel_version_info
from ipykernel.ipkernel import IPythonKernel
from IPython.utils.tokenutil import line_at_cursor, token_at_cursor
from jupyter_client import manager
from sos._version import __sos_version__, __version__
from sos.eval import SoS_eval, interpolate
from sos.executor_utils import prepare_env
from sos.syntax import SOS_DIRECTIVE, SOS_SECTION_HEADER
from sos.utils import env, load_config_files, short_repr

from ._version import __version__ as __notebook_version__
from .comm_manager import SoSCommManager
from .completer import SoS_Completer
from .inspector import SoS_Inspector
from .magics import SoS_Magics
from .workflow_executor import (NotebookLoggingHandler, execute_scratch_cell, run_sos_workflow, start_controller)
from .subkernel import Subkernels

class FlushableStringIO:

    def __init__(self, kernel, name, *args, **kwargs):
        self.kernel = kernel
        self.name = name

    def write(self, content):
        if content.startswith('HINT: '):
            content = content.splitlines()
            hint_line = content[0][6:].strip()
            content = '\n'.join(content[1:])
            self.kernel.send_response(self.kernel.iopub_socket, 'display_data', {
                'metadata': {},
                'data': {
                    'text/html': f'<div class="sos_hint">{hint_line}</div>'
                }
            })
        if content:
            if self.kernel._meta['capture_result'] is not None:
                self.kernel._meta['capture_result'].append(('stream', {'name': self.name, 'text': content}))
            if self.kernel._meta['render_result'] is False:
                self.kernel.send_response(self.kernel.iopub_socket, 'stream', {'name': self.name, 'text': content})

    def flush(self):
        pass


__all__ = ['SoS_Kernel']

# translate a message to transient_display_data message


def make_transient_msg(msg_type, content):
    if msg_type == 'display_data':
        return {'data': content.get('data', {}), 'metadata': content.get('metadata', {})}
    if msg_type == 'stream':
        if content['name'] == 'stdout':
            return {
                'data': {
                    'text/plain': content['text'],
                    'application/vnd.jupyter.stdout': content['text']
                },
                'metadata': {}
            }
        return {
            'data': {
                'text/plain': content['text'],
                'application/vnd.jupyter.stderr': content['text']
            },
            'metadata': {}
        }
    raise ValueError(f"failed to translate message {msg_type} to transient_display_data message")


class SoS_Kernel(IPythonKernel):
    implementation = 'SOS'
    implementation_version = __version__
    language = 'sos'
    language_version = __sos_version__
    language_info = {
        'mimetype': 'text/x-sos',
        'name': 'sos',
        'file_extension': '.sos',
        'pygments_lexer': 'sos',
        'codemirror_mode': 'sos',
        'nbconvert_exporter': 'sos_notebook.converter.SoS_Exporter',
    }
    banner = "SoS kernel - script of scripts"

    def get_supported_languages(self):
        if self._supported_languages is not None:
            return self._supported_languages
        group = 'sos_languages'
        self._supported_languages = {}

        for entrypoint in pkg_resources.iter_entry_points(group=group):
            # Grab the function that is the actual plugin.
            name = entrypoint.name
            env.log_to_file('KERNEL', f'Found registered language {name}')
            try:
                plugin = entrypoint.load()
                self._supported_languages[name] = plugin
            except Exception as e:
                env.log_to_file('KERNEL', f'Failed to load registered language {name}: {e}')
                self._failed_languages[name] = e
        return self._supported_languages

    supported_languages = property(lambda self: self.get_supported_languages())

    def get_kernel_list(self):
        if not hasattr(self, '_subkernels'):
            self._subkernels = Subkernels(self)

        # sort kernel list by name to avoid unnecessary change of .ipynb files
        return self._subkernels

    subkernels = property(lambda self: self.get_kernel_list())

    def get_completer(self):
        if self._completer is None:
            self._completer = SoS_Completer(self)
        return self._completer

    completer = property(lambda self: self.get_completer())

    def get_inspector(self):
        if self._inspector is None:
            self._inspector = SoS_Inspector(self)
        return self._inspector

    inspector = property(lambda self: self.get_inspector())

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.options = ''
        self.kernel = 'SoS'
        # a dictionary of started kernels, with the format of
        #
        # 'R': ['ir', 'sos.R.sos_R', '#FFEEAABB']
        #
        # Note that:
        #
        # 'R' is the displayed name of the kernel.
        # 'ir' is the kernel name.
        # 'sos.R.sos_R' is the language module.
        # '#FFEEAABB' is the background color
        #
        env.log_to_file('KERNEL', f'Starting SoS Kernel version {__notebook_version__} with SoS {__version__}')

        self.kernels = {}
        # self.shell = InteractiveShell.instance()
        self.format_obj = self.shell.display_formatter.format

        self._meta = {
            'workflow': '',
            'workflow_mode': False,
            'render_result': False,
            'capture_result': None,
            'cell_id': '0',
            'notebook_name': '',
            'notebook_path': '',
            'use_panel': True,
            'use_iopub': False,
            'default_kernel': 'SoS',
            'cell_kernel': 'SoS',
            'batch_mode': False
        }
        self._debug_mode = False
        self._supported_languages = None
        self._completer = None
        self._inspector = None
        self._real_execution_count = 1
        self._execution_count = 1
        self.frontend_comm = None
        self.frontend_comm_cache = []

        #
        self.comm_manager = comm.get_comm_manager()
        # remove the old comm_manager
        self.shell.configurables.pop()
        self.shell.configurables.append(self.comm_manager)
        for msg_type in ['comm_open', 'comm_msg', 'comm_close']:
            self.shell_handlers[msg_type] = getattr(self.comm_manager, msg_type)

        self.comm_manager.register_target('sos_comm', self.sos_comm)
        self.my_tasks = {}
        self.magics = SoS_Magics(self)
        self._failed_languages = {}
        # enable matplotlib by default #77
        self.shell.enable_gui = lambda gui: None
        self.editor_kernel = 'sos'
        # initialize env
        prepare_env('')
        self.original_keys = set(env.sos_dict._dict.keys()) | {
            'SOS_VERSION', 'CONFIG', 'step_name', '__builtins__', 'input', 'output', 'depends'
        }
        env.logger.handlers = [x for x in env.logger.handlers if not isinstance(x, logging.StreamHandler)]
        env.logger.addHandler(
            NotebookLoggingHandler(
                {
                    0: logging.ERROR,
                    1: logging.WARNING,
                    2: logging.INFO,
                    3: logging.DEBUG,
                    4: logging.DEBUG,
                    None: logging.INFO
                }[env.verbosity],
                kernel=self))
        env.logger.print = lambda cell_id, msg, *args: \
            self.send_response(self.iopub_socket, 'stream', {'name': 'stdout', 'text': msg}) if self._meta['batch_mode'] else self.send_frontend_msg('print', [cell_id, msg])
        self.controller = None

    cell_id = property(lambda self: self._meta['cell_id'])
    _workflow_mode = property(lambda self: self._meta['workflow_mode'])

    def sos_comm(self, comm, msg):
        # record frontend_comm to send messages
        self.frontend_comm = comm

        @comm.on_msg
        def handle_frontend_msg(msg):
            content = msg['content']['data']
            # log_to_file(msg)
            for k, v in content.items():
                if k == 'list-kernel':
                    if v:
                        self.subkernels.update(v)
                    self.subkernels.notify_frontend()
                elif k == 'set-editor-kernel':
                    self.editor_kernel = v
                elif k == 'cancel-workflow':
                    from .workflow_executor import cancel_workflow
                    cancel_workflow(v[0], self)
                elif k == 'execute-workflow':
                    from .workflow_executor import execute_pending_workflow
                    execute_pending_workflow(v, self)
                elif k == 'update-task-status':
                    if not isinstance(v, list):
                        env.log_to_file('KERNEL', f'Failed to parse message for update-task-status {v}')
                        continue
                    # split by host ...
                    host_status = defaultdict(list)
                    for name in v:
                        try:
                            tqu, tid, _ = name.rsplit('_', 2)
                        except Exception as e:
                            env.log_to_file('KERNEL', f'Failed to parse task ID {name}: {e}')
                            # incorrect ID...
                            continue
                        host_status[tqu].append(tid)
                    # log_to_file(host_status)
                    #
                    from sos.hosts import Host
                    for tqu, tids in host_status.items():
                        try:
                            h = Host(tqu, start_engine=True)
                        except Exception as e:
                            env.log_to_file('KERNEL', f'Failed to connect to host {tqu}: {e}')
                            for tid in tids:
                                self.send_frontend_msg('task_status', {
                                    'task_id': tid,
                                    'queue': tqu,
                                    'status': 'missing',
                                    'duration': ''
                                })
                            continue
                        for tid, tst, tdt in h._task_engine.monitor_tasks(tids):
                            self.send_frontend_msg('task_status', {
                                'task_id': tid,
                                'queue': tqu,
                                'status': tst,
                                'duration': tdt
                            })

                    self.send_frontend_msg('update-duration', {})
                elif k == 'paste-table':
                    try:
                        from tabulate import tabulate
                        df = pd.read_clipboard()
                        tbl = tabulate(df, headers='keys', tablefmt='pipe')
                        self.send_frontend_msg('paste-table', tbl)
                    except Exception as e:
                        self.send_frontend_msg('alert', f'Failed to paste clipboard as table: {e}')
                elif k == 'notebook-version':
                    # send the version of notebook, right now we will not do anything to it, but
                    # we will send the version of sos-notebook there
                    self.send_frontend_msg('notebook-version', __notebook_version__)
                else:
                    # this somehow does not work
                    self.warn(f'Unknown message {k}: {v}')

    def notify_error(self, e):
        msg = {
            'status': 'error',
            'ename': e.__class__.__name__,
            'evalue': str(e),
            'traceback': [f'\033[91m{e}\033[0m'],
            'execution_count': self._execution_count,
        }
        if self._meta['suppress_error']:
            self.send_response(self.iopub_socket, 'stream', {
                'name': 'stderr',
                'text': f"{msg['ename']}: {msg['evalue']}"
            })
        else:
            self.send_response(self.iopub_socket, 'error', msg)
        return msg

    def send_frontend_msg(self, msg_type, msg=None):
        # if comm is never created by frontend, the kernel is in test mode without frontend
        if msg_type in ('display_data', 'stream'):
            if self._meta['use_panel'] is False or self._meta['cell_id'] == -1:
                self.send_response(self.iopub_socket, msg_type, {} if msg is None else msg)
            elif self._meta['use_iopub']:
                self.send_response(self.iopub_socket, 'transient_display_data', make_transient_msg(msg_type, msg))
            elif self.frontend_comm:
                if self.frontend_comm_cache:
                    for mt, mg in self.frontend_comm_cache:
                        self.frontend_comm.send(make_transient_msg(mt, mg), {'msg_type': 'transient_display_data'})
                    self.frontend_comm_cache = []
                self.frontend_comm.send(make_transient_msg(msg_type, msg), {'msg_type': 'transient_display_data'})
            elif self._meta['batch_mode']:
                env.log_to_file('MESSAGE', f'frontend message of type {msg_type} is sent in batch mode.')
            else:
                self.frontend_comm_cache.append([msg_type, msg])
                env.log_to_file('MESSAGE', f'fronten not ready or broken. Message of type {msg_type} is cached')
        elif self.frontend_comm:
            if self.frontend_comm_cache:
                for mt, mg in self.frontend_comm_cache:
                    self.frontend_comm.send({} if mg is None else mg, {'msg_type': mt})
                self.frontend_comm_cache = []
            self.frontend_comm.send({} if msg is None else msg, {'msg_type': msg_type})
        elif self._meta['batch_mode']:
            env.log_to_file('MESSAGE', f'frontend message of type {msg_type} is sent in batch mode.')
        else:
            # frontend_comm is not ready
            self.frontend_comm_cache.append([msg_type, msg])
            env.log_to_file('MESSAGE', f'fronten not ready or broken. Message of type {msg_type} is cached')

    @contextlib.contextmanager
    def redirect_sos_io(self):
        save_stdout = sys.stdout
        save_stderr = sys.stderr
        sys.stdout = FlushableStringIO(self, 'stdout')
        sys.stderr = FlushableStringIO(self, 'stderr')
        yield
        sys.stdout = save_stdout
        sys.stderr = save_stderr

    async def get_vars_from(self, items, from_kernel=None, explicit=False, as_var=None):
        if as_var is not None:
            if not isinstance(as_var, str):
                self.warn('Option --as should be a string.')
                return
            if len(items) > 1:
                self.warn('Only one expression is allowed when option --as is used')
                return
        if from_kernel is None or from_kernel.lower() == 'sos':
            # Feature removed #253
            # autmatically get all variables with names start with 'sos'
            # default_items = [
            #     x for x in env.sos_dict.keys()
            #     if x.startswith('sos') and x not in self.original_keys
            # ]
            if not items:
                return
            for item in items:
                if item not in env.sos_dict:
                    self.warn(f'Variable {item} does not exist')
                    return
            kinfo = self.subkernels.find(self.kernel)
            if kinfo.language in self.supported_languages:
                lan = self.supported_languages[kinfo.language]
                try:
                    get_vars_func = lan(self, kinfo.kernel).get_vars
                    args = inspect.getfullargspec(get_vars_func).args
                    if 'as_var' in args:
                        await get_vars_func(items, as_var=as_var)
                    else:
                        if as_var is not None:
                            self.warn(f'Subkernel {kinfo.language} does not support option --as')
                        await get_vars_func(items)
                except Exception as e:
                    self.warn(f'Failed to get variable: {e}\n')
                    return
            elif self.kernel == 'SoS':
                self.warn('Magic %get without option --kernel can only be executed by subkernels')
                return
            else:
                if explicit:
                    self.warn(
                        f'Magic %get failed because the language module for {self.kernel} is not properly installed. Please install it according to language specific instructions on the Running SoS section of the SoS homepage and restart Jupyter server.'
                    )
                return
        elif self.kernel.lower() == 'sos':
            # if another kernel is specified and the current kernel is sos
            # we get from subkernel
            try:
                await self.switch_kernel(from_kernel)
                await self.put_vars_to(items, as_var=as_var)
            except Exception as e:
                self.warn(f'Failed to get {", ".join(items)} from {from_kernel}: {e}')
            finally:
                await self.switch_kernel('SoS')
        else:
            # if another kernel is specified, we should try to let that kernel pass
            # the variables to this one directly
            try:
                my_kernel = self.kernel
                await self.switch_kernel(from_kernel)
                # put stuff to sos or my_kernel directly
                await self.put_vars_to(items, to_kernel=my_kernel, explicit=explicit, as_var=as_var)
            except Exception as e:
                self.warn(f'Failed to get {", ".join(items)} from {from_kernel}: {e}')
            finally:
                # then switch back
                await self.switch_kernel(my_kernel)

    async def put_vars_to(self, items, to_kernel=None, explicit=False, as_var=None):
        if not items:
            return
        if as_var is not None:
            if not isinstance(as_var, str):
                self.warn('Option --as should be a string.')
                return
            if len(items) > 1:
                self.warn('Only one expression is allowed when option --as is used')
                return
        if self.kernel.lower() == 'sos':
            if to_kernel is None:
                self.warn('Magic %put without option --kernel can only be executed by subkernels')
                return
            # if another kernel is specified and the current kernel is sos
            try:
                # switch to kernel and bring in items
                await self.switch_kernel(to_kernel, in_vars=items, as_var=as_var)
            except Exception as e:
                self.warn(f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
            finally:
                # switch back
                await self.switch_kernel('SoS')
        else:
            # put to sos kernel or another kernel
            kinfo = self.subkernels.find(self.kernel)
            if kinfo.language not in self.supported_languages:
                if explicit:
                    self.warn(f'Subkernel {self.kernel} does not support magic %put.')
                return
            #
            lan = self.supported_languages[kinfo.language]
            # pass language name to to_kernel
            try:
                put_vars_func = lan(self, kinfo.kernel).put_vars
                args = inspect.getfullargspec(put_vars_func).args
                to_kernel_name = self.subkernels.find(to_kernel).language if to_kernel else 'SoS'
                if 'as_var' in args:
                    objects = put_vars_func(items, to_kernel=to_kernel_name, as_var=as_var)
                else:
                    objects = put_vars_func(items, to_kernel=to_kernel_name)

            except Exception as e:
                # if somethign goes wrong in the subkernel does not matter
                env.log_to_file('MAGIC', f'Failed to call put_var({items}) from {kinfo.kernel}: {e}')
                objects = {}
            if isinstance(objects, dict):
                # returns a SOS dictionary
                try:
                    # if the variable is passing through SoS, let us try to restore variables in SoS
                    if to_kernel is not None:
                        missing_vars = [x for x in objects.keys() if x not in env.sos_dict]
                        existing_vars = {x: env.sos_dict[x] for x in objects.keys() if x in env.sos_dict}
                    env.sos_dict.update(objects)
                except Exception as e:
                    self.warn(f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                    return

                if to_kernel is None:
                    return
                # if another kernel is specified and the current kernel is not sos
                # we need to first put to sos then to another kernel
                my_kernel = self.kernel
                try:
                    # switch to the destination kernel and bring in vars
                    await self.switch_kernel(to_kernel, in_vars=[as_var] if as_var else items)
                except Exception as e:
                    self.warn(f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                finally:
                    # switch back to the original kernel
                    await self.switch_kernel(my_kernel)
                    # restore sos_dict to avoid bypassing effect #252
                    for missing_var in missing_vars:
                        env.sos_dict.pop(missing_var)
                    env.sos_dict.update(existing_vars)
            elif isinstance(objects, str):
                # an statement that will be executed in the destination kernel
                if to_kernel is None or to_kernel == 'SoS':
                    # evaluate in SoS, this should not happen or rarely happen
                    # because the subkernel should return a dictionary for SoS kernel
                    try:
                        exec(objects, env.sos_dict._dict)
                    except Exception as e:
                        self.warn(f'Failed to put variables {items} to SoS kernel: {e}')
                        return
                try:
                    my_kernel = self.kernel
                    # switch to the destination kernel
                    await self.switch_kernel(to_kernel)
                    # execute the statement to pass variables directly to destination kernel
                    await self.run_cell(objects, True, False)
                except Exception as e:
                    self.warn(f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                finally:
                    # switch back to the original kernel
                    await self.switch_kernel(my_kernel)
            else:
                self.warn(f'Unrecognized return value of type {object.__class__.__name__} for action %put')

    async def expand_text_in(self, text, sigil=None, kernel='SoS'):
        '''
        Expand a piece of (markdown) text in specified kernel, used by
        magic %expand
        '''
        if not text:
            return ''
        if sigil is None:
            sigil = '{ }'
        if sigil.count(' ') != 1:
            raise ValueError(f'Invalid interpolation delimiter "{sigil}": should be in the format of "L R"')
        if sigil.split(' ')[0] not in text:
            return text

        if not kernel or kernel.lower() == 'sos':
            if sigil != '{ }':
                from sos.parser import replace_sigil
                text = replace_sigil(text, sigil)
            return interpolate(text, local_dict=env.sos_dict._dict)
        # check if the language supports expand protocol
        kinfo = self.subkernels.find(kernel)
        if kinfo.language not in self.supported_languages:
            self.warn(f'Subkernel {kernel} does not support magic %expand --in')
            return text
        lan = self.supported_languages[kinfo.language](self, kinfo.kernel)
        if not hasattr(lan, 'expand'):
            self.warn(f'Subkernel {kernel} does not support magic %expand --in')
            return text
        orig_kernel = self.kernel
        try:
            await self.switch_kernel(kernel)
            return lan.expand(text, sigil)
        except Exception as e:
            self.warn(f'Failed to expand {text} with sigin {sigil} in kernel {kernel}: {e}')
            return text
        finally:
            await self.switch_kernel(orig_kernel)

    def do_is_complete(self, code):
        '''check if new line is in order'''
        code = code.strip()
        if not code:
            return {'status': 'complete', 'indent': ''}

        env.log_to_file('MESSAGE', f'Checking is_complete of "{code}"')
        lines = code.split('\n')
        # first let us remove "valid" magics
        while any(line.startswith('%') or line.startswith('!') for line in lines):
            for idx, line in enumerate(lines):
                if line.startswith('%') or line.startswith('!'):
                    # if the last line ending with \, incomplete
                    if line.endswith('\\'):
                        if idx == len(lines) - 1:
                            return {'status': 'incomplete', 'indent': ''}
                        lines[idx] = lines[idx][:-1] + lines[idx + 1]
                        lines[idx + 1] = ''
                    else:
                        # valid, complete, ignore
                        lines[idx] = ''

        if self.kernel == 'SoS':
            for idx, line in enumerate(lines):
                # remove header
                if SOS_SECTION_HEADER.match(line):
                    lines[idx] = ''
                # remove input stuff?
                if SOS_DIRECTIVE.match(line):
                    if any(line.startswith(x) for x in ('input:', 'output:', 'depends:', 'parameter:')):
                        # directive, remvoe them
                        lines[idx] = lines[idx].split(':', 1)[-1]
                    elif idx == len(lines) - 1:
                        # sh: with no script, incomplete
                        return {'status': 'incomplete', 'indent': '  '}
                    else:
                        # remove the rest of them because they are embedded script
                        for i in range(idx, len(lines)):
                            lines[i] = ''
            # check the rest if it is ok
            try:
                from IPython.core.inputtransformer2 import \
                    TransformerManager as ipf
            except ImportError:
                from IPython.core.inputsplitter import InputSplitter as ipf
            code = '\n'.join(lines) + '\n\n'
            res = ipf().check_complete(code)
            env.log_to_file('MESSAGE', f'SoS kernel returns {res} for code {code}')
            return {'status': res[0], 'indent': res[1]}
        # non-SoS kernels
        try:
            cell_kernel = self.subkernels.find(self.editor_kernel)
            if cell_kernel.name not in self.kernels:
                orig_kernel = self.kernel
                try:
                    # switch to start the new kernel
                    asyncio.run(self.switch_kernel(cell_kernel.name))
                finally:
                    asyncio.run(self.switch_kernel(orig_kernel))

            KC = self.kernels[cell_kernel.name][1]
            # clear the shell channel
            while KC.shell_channel.msg_ready():
                KC.shell_channel.get_msg()
            code = '\n'.join(lines)
            KC.is_complete(code)
            msg = KC.shell_channel.get_msg()
            if msg['header']['msg_type'] == 'is_complete_reply':
                env.log_to_file('MESSAGE', f'{self.kernel} kernel returns {msg["content"]} for code {code}')
                return msg['content']

            raise RuntimeError(
                f"is_complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead")
        except Exception as e:
            env.logger.debug(f'Completion fail with exception: {e}')
            return {'status': 'incomplete', 'indent': ''}

    def do_inspect(self, code, cursor_pos, detail_level=0):
        if self.editor_kernel.lower() == 'sos':
            line, offset = line_at_cursor(code, cursor_pos)
            name = token_at_cursor(code, cursor_pos)
            data = self.inspector.inspect(name, line, cursor_pos - offset)
            return {'status': 'ok', 'metadata': {}, 'found': True if data else False, 'data': data}
        cell_kernel = self.subkernels.find(self.editor_kernel)
        try:
            _, KC = self.kernels[cell_kernel.name]
        except Exception as e:
            env.log_to_file('KERNEL', f'Failed to get subkernels {cell_kernel.name}: {e}')
            KC = self.KC
        try:
            KC.inspect(code, cursor_pos)
            while KC.shell_channel.msg_ready():
                msg = KC.shell_channel.get_msg()
                if msg['header']['msg_type'] == 'inspect_reply':
                    return msg['content']
                # other messages, do not know what is going on but
                # we should not wait forever and cause a deadloop here
                env.log_to_file(
                    'MESSAGE',
                    f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead")
                break
        except Exception as e:
            env.log_to_file('KERNEL', f'Completion fail with exception: {e}')

    async def do_complete(self, code, cursor_pos):
        if self.editor_kernel.lower() == 'sos':
            text, matches = self.completer.complete_text(code, cursor_pos)
            return {
                'matches': matches,
                'cursor_end': cursor_pos,
                'cursor_start': cursor_pos - len(text),
                'metadata': {},
                'status': 'ok'
            }
        try:
            cell_kernel = self.subkernels.find(self.editor_kernel)
            if cell_kernel.name not in self.kernels:
                orig_kernel = self.kernel
                try:
                    # switch to start the new kernel
                    await self.switch_kernel(cell_kernel.name)
                finally:
                    await self.switch_kernel(orig_kernel)

            KC = self.kernels[cell_kernel.name][1]
            # clear the shell channel
            while KC.shell_channel.msg_ready():
                KC.shell_channel.get_msg()
            KC.complete(code, cursor_pos)
            msg = KC.shell_channel.get_msg()
            if msg['header']['msg_type'] == 'complete_reply':
                return msg['content']

            raise RuntimeError(
                f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead")
        except Exception as e:
            env.logger.debug(f'Completion fail with exception: {e}')
            return {
                'matches': [],
                'cursor_end': cursor_pos,
                'cursor_start': cursor_pos,
                'metadata': {},
                'status': 'error'
            }

    def warn(self, message):
        message = str(message).rstrip() + '\n'
        if message.strip():
            self.send_response(self.iopub_socket, 'stream', {'name': 'stderr', 'text': message})

    async def run_cell(self, code, silent, store_history, on_error=None):
        #
        if not self.KM.is_alive():
            self.send_response(self.iopub_socket, 'stream',
                               dict(name='stdout', text='Restarting kernel "{}"\n'.format(self.kernel)))
            self.KM.restart_kernel(now=False)
            self.KC = self.KM.client()
        # flush stale replies, which could have been ignored, due to missed heartbeats
        while self.KC.shell_channel.msg_ready():
            self.KC.shell_channel.get_msg()
        # executing code in another kernel.
        # https://github.com/ipython/ipykernel/blob/604ee892623cca29eb495933eb5aa26bd166c7ff/ipykernel/inprocess/client.py#L94
        content = dict(code=code, silent=silent, store_history=store_history, user_expressions={}, allow_stdin=False)
        msg = self.KC.session.msg('execute_request', content)
        # use the msg_id of the sos kernel for the subkernel to make sure that the messages sent
        # from the subkernel has the correct msg_id in parent_header so that they can be
        # displayed directly in the notebook (without using self._parent_header
        if ipykernel_version_info[0] >= 6:
            msg['msg_id'] = self.get_parent()['header']['msg_id']
        else:
            msg['msg_id'] = self._parent_header['header']['msg_id']
        msg['header']['msg_id'] = msg['msg_id']
        self.KC.shell_channel.send(msg)

        # first thing is wait for any side effects (output, stdin, etc.)
        iopub_started = False
        iopub_ended = False
        shell_ended = False
        res = None
        while not (iopub_started and iopub_ended and shell_ended):
            try:
                # display intermediate print statements, etc.
                while self.KC.stdin_channel.msg_ready():
                    sub_msg = self.KC.stdin_channel.get_msg()
                    env.log_to_file('MESSAGE',
                                    f"MSG TYPE {sub_msg['header']['msg_type']} CONTENT\n  {pprint.pformat(sub_msg)}")
                    if sub_msg['header']['msg_type'] != 'input_request':
                        self.session.send(self.stdin_socket, sub_msg)
                    else:
                        content = sub_msg["content"]
                        if content['password']:
                            res = self.getpass(prompt=content['prompt'])
                        else:
                            res = self.raw_input(prompt=content['prompt'])
                        self.KC.input(res)
                while self.KC.iopub_channel.msg_ready():
                    sub_msg = self.KC.iopub_channel.get_msg()
                    msg_type = sub_msg['header']['msg_type']
                    env.log_to_file(
                        'MESSAGE',
                        f"IOPUB MSG TYPE {sub_msg['header']['msg_type']} CONTENT  \n {pprint.pformat(sub_msg)}")
                    if msg_type == 'status':
                        if sub_msg["content"]["execution_state"] == 'busy':
                            iopub_started = True
                        elif iopub_started and sub_msg["content"]["execution_state"] == 'idle':
                            iopub_ended = True
                        continue
                    if msg_type in ('execute_input', 'execute_result'):
                        # override execution count with the master count,
                        # not sure if it is needed
                        sub_msg['content']['execution_count'] = self._execution_count
                    #
                    if msg_type in ['display_data', 'stream', 'execute_result', 'update_display_data', 'error']:
                        if self._meta['capture_result'] is not None:
                            self._meta['capture_result'].append((msg_type, sub_msg['content']))
                        if msg_type == 'execute_result' or (not silent and self._meta['render_result'] is False):
                            if msg_type == 'error' and self._meta['suppress_error']:
                                self.send_response(
                                    self.iopub_socket, 'stream', {
                                        'name': 'stderr',
                                        'text': f"{sub_msg['content']['ename']}: {sub_msg['content']['evalue']}"
                                    })
                            else:
                                self.session.send(self.iopub_socket, sub_msg)
                    else:
                        # if the subkernel tried to create a customized comm
                        if msg_type == 'comm_open':
                            self.comm_manager.register_subcomm(sub_msg['content']['comm_id'], self.KC, self)
                        self.session.send(self.iopub_socket, sub_msg)
                if self.KC.shell_channel.msg_ready():
                    # now get the real result
                    reply = self.KC.get_shell_msg()
                    reply['content']['execution_count'] = self._execution_count
                    env.log_to_file('MESSAGE', f'GET SHELL MSG {pprint.pformat(reply)}')
                    res = reply['content']
                    shell_ended = True
                time.sleep(0.001)
            except KeyboardInterrupt:
                self.KM.interrupt_kernel()
        return res

    def get_info_of_subkernels(self):
        from jupyter_client.kernelspec import KernelSpecManager
        km = KernelSpecManager()

        available_subkernels = '''<table>
            <tr>
                <th>Subkernel</th>
                <th>Kernel Name</th>
                <th>Language</th>
                <th>Language Module</th>
                <th  style="text-align:left">Interpreter</th>
            </tr>'''
        for sk in self.subkernels.kernel_list():
            spec = km.get_kernel_spec(sk.kernel)
            if sk.name in ('SoS', 'Markdown'):
                lan_module = ''
            elif sk.language in self.supported_languages:
                lan_module = f"<code>{self.supported_languages[sk.language].__module__.split('.')[0]}</code>"
            else:
                lan_module = '<font style="color:red">Unavailable</font>'
            available_subkernels += f'''\
        <tr>
        <td>{sk.name}</td>
        <td><code>{sk.kernel}</code></td>
        <td>{spec.language}</td>
        <td>{lan_module}</td>
        <td style="text-align:left"><code>{spec.argv[0]}</code></td>
        </tr>'''
        available_subkernels += '</table>'
        return available_subkernels

    async def switch_kernel(self, kernel, in_vars=None, kernel_name=None, language=None, color=None, as_var=None):
        # switching to a non-sos kernel
        if not kernel:
            kinfo = self.subkernels.find(self.kernel)
            self.send_response(self.iopub_socket, 'display_data',
                               dict(metadata={}, data={'text/html': self.get_info_of_subkernels()}))
            return
        kinfo = self.subkernels.find(kernel, kernel_name, language, color)
        if kinfo.name == self.kernel:
            return
        if kinfo.name == 'SoS':
            # non-SoS to SoS
            if in_vars:
                await self.put_vars_to(in_vars, as_var=as_var)
            self.kernel = 'SoS'
        elif self.kernel != 'SoS':
            # Non-SoS to Non-SoS
            await self.switch_kernel('SoS', in_vars)
            await self.switch_kernel(kinfo.name, in_vars)
        else:
            # SoS to non-SoS
            env.log_to_file('KERNEL', f'Switch from {self.kernel} to {kinfo.name}')
            # case when self.kernel == 'sos', kernel != 'sos'
            # to a subkernel
            new_kernel = False
            if kinfo.name not in self.kernels:
                # start a new kernel
                try:
                    env.log_to_file('KERNEL', f'Starting subkernel {kinfo.name}')
                    self.kernels[kinfo.name] = manager.start_new_kernel(
                        startup_timeout=30, kernel_name=kinfo.kernel, cwd=os.getcwd())
                    new_kernel = True
                except Exception as e:
                    env.log_to_file('KERNEL', f'Failed to start kernel {kinfo.kernel}. Trying again...')
                    # try toget error message
                    import tempfile
                    with tempfile.TemporaryFile() as ferr:
                        try:
                            # this should fail, but sometimes the second attempt will succeed #282
                            self.kernels[kinfo.name] = manager.start_new_kernel(
                                startup_timeout=60,
                                kernel_name=kinfo.kernel,
                                cwd=os.getcwd(),
                                stdout=subprocess.DEVNULL,
                                stderr=ferr)
                            new_kernel = True
                            env.log_to_file('KERNEL', f'Kernel {kinfo.kernel} started with the second attempt.')
                        except Exception as e:
                            ferr.seek(0)
                            raise RuntimeError(
                                f'Failed to start kernel "{kernel}". {e}\nError Message:\n{ferr.read().decode()}'
                            ) from e
            self.KM, self.KC = self.kernels[kinfo.name]
            self.kernel = kinfo.name
            if new_kernel and not kinfo.codemirror_mode:
                self.KC.kernel_info()
                kinfo.codemirror_mode = self.KC.get_shell_msg(timeout=10)['content']['language_info'].get(
                    'codemirror_mode', '')
                self.subkernels.notify_frontend()
            if new_kernel and kinfo.language in self.supported_languages:
                lan_module = self.supported_languages[kinfo.language](self, kinfo.kernel)
                init_stmts = lan_module.init_statements

                if hasattr(lan_module, '__version__'):
                    module_version = f' (version {lan_module.__version__})'
                else:
                    module_version = ' (version unavailable)'

                env.log_to_file('KERNEL', f'Loading language module for kernel {kinfo.name}{module_version}')
                if init_stmts:
                    await self.run_cell(init_stmts, True, False)
            # passing
            if in_vars:
                await self.get_vars_from(in_vars, as_var=as_var)

    def shutdown_kernel(self, kernel, restart=False):
        kernel = self.subkernels.find(kernel).name
        if kernel == 'SoS':
            # cannot restart myself ...
            self.warn('Cannot restart SoS kernel from within SoS.')
        elif kernel:
            if kernel not in self.kernels:
                self.send_response(self.iopub_socket, 'stream', dict(name='stdout', text=f'{kernel} is not running'))
            elif restart:
                orig_kernel = self.kernel
                try:
                    # shutdown
                    self.shutdown_kernel(kernel)
                    # switch back to kernel (start a new one)
                    asyncio.run(self.switch_kernel(kernel))
                finally:
                    # finally switch to starting kernel
                    asyncio.run(self.switch_kernel(orig_kernel))
            else:
                # shutdown
                if self.kernel == kernel:
                    asyncio.run(self.switch_kernel('SoS'))
                try:
                    self.kernels[kernel][0].shutdown_kernel(restart=False)
                except Exception as e:
                    self.warn(f'Failed to shutdown kernel {kernel}: {e}\n')
                finally:
                    self.kernels.pop(kernel)
        else:
            self.send_response(
                self.iopub_socket, 'stream',
                dict(
                    name='stdout',
                    text='Specify one of the kernels to shutdown: SoS{}\n'.format(''.join(
                        f', {x}' for x in self.kernels))))
        # stop_controller(self.controller)

    # def get_response(self, statement, msg_types, name=None):
    #     return asyncio.run(self._async_get_response(statement, msg_types, name))

    def get_response(self, statement, msg_types, name=None):
        # get response of statement of specific msg types.
        while self.KC.shell_channel.msg_ready():
            self.KC.shell_channel.get_msg()
        while self.KC.iopub_channel.msg_ready():
            sub_msg = self.KC.iopub_channel.get_msg()
            if sub_msg['header']['msg_type'] != 'status':
                env.log_to_file('MESSAGE',
                                f"Overflow message in iopub {sub_msg['header']['msg_type']} {sub_msg['content']}")
        responses = []
        self.KC.execute(statement, silent=False, store_history=False)
        # first thing is wait for any side effects (output, stdin, etc.)
        iopub_started = False
        iopub_ended = False
        shell_ended = False
        while not (iopub_started and iopub_ended and shell_ended):
            # display intermediate print statements, etc.
            while self.KC.iopub_channel.msg_ready():
                sub_msg = self.KC.iopub_channel.get_msg()
                msg_type = sub_msg['header']['msg_type']
                env.log_to_file('MESSAGE', f'Received {msg_type} {sub_msg["content"]}')
                if msg_type == 'status':
                    if sub_msg["content"]["execution_state"] == 'busy':
                        iopub_started = True
                    elif iopub_started and sub_msg["content"]["execution_state"] == 'idle':
                        iopub_ended = True
                    continue
                if msg_type in msg_types and (name is None or sub_msg['content'].get('name', None) in name or
                                              any(x in name for x in sub_msg['content'].keys())):
                    env.log_to_file('MESSAGE', f'Capture response: {msg_type}: {sub_msg["content"]}')
                    responses.append([msg_type, sub_msg['content']])
                else:
                    env.log_to_file('MESSAGE', f'Non-response: {msg_type}: {sub_msg["content"]}')
                    #
                    # we ignore the messages we are not interested.
                    #
                    # self.send_response(
                    #    self.iopub_socket, msg_type, sub_msg['content'])
            if self.KC.shell_channel.msg_ready():
                # now get the real result
                reply = self.KC.get_shell_msg()
                env.log_to_file('MESSAGE', f'GET SHELL MSG {reply}')
                shell_ended = True
            time.sleep(0.001)

        if not responses:
            env.log_to_file('MESSAGE',
                            f'Failed to get a response from message type {msg_types} for the execution of {statement}')
        return responses

    def run_sos_code(self, code, silent):
        code = dedent(code)
        with self.redirect_sos_io():
            try:
                if self._workflow_mode:
                    res = run_sos_workflow(
                        code=code,
                        raw_args=self.options,
                        kernel=self,
                        run_in_queue=self._workflow_mode == 'nowait' and not self._meta['batch_mode'])
                else:
                    res = execute_scratch_cell(code=code, raw_args=self.options, kernel=self)
                self.send_result(res, silent)
            except Exception as e:
                sys.stderr.flush()
                sys.stdout.flush()
                raise e
            except KeyboardInterrupt:
                # this only occurs when the executor does not capture the signal.
                self.warn('KeyboardInterrupt\n')
                return {'status': 'abort', 'execution_count': self._execution_count}
            finally:
                sys.stderr.flush()
                sys.stdout.flush()

    def render_result(self, res):
        if not self._meta['render_result']:
            return res
        if not isinstance(res, str):
            self.warn(
                f'Cannot render result {short_repr(res)} in type {res.__class__.__name__} as {self._meta["render_result"]}.'
            )
        else:
            # import the object from IPython.display
            mod = __import__('IPython.display')
            if not hasattr(mod.display, self._meta['render_result']):
                self.warn(f'Unrecognized render format {self._meta["render_result"]}')
            else:
                func = getattr(mod.display, self._meta['render_result'])
                res = func(res)
        return res

    def send_result(self, res, silent=False):
        # this is Ok, send result back
        if not silent and res is not None:
            format_dict, md_dict = self.format_obj(self.render_result(res))
            if self._meta['capture_result'] is not None:
                self._meta['capture_result'].append(('execute_result', format_dict))
            env.log_to_file('MESSAGE', f'IOPUB execute_result with content {format_dict}')
            self.send_response(self.iopub_socket, 'execute_result', {
                'execution_count': self._execution_count,
                'data': format_dict,
                'metadata': md_dict
            })

    def init_metadata(self, metadata):
        super().init_metadata(metadata)
        env.log_to_file('KERNEL', f'GOT METADATA {metadata}')
        if 'sos' in metadata['metadata']:
            # jupyterlab-sos sends meta data through metadata
            meta = metadata['metadata']['sos']
        elif 'sos' in metadata['content']:
            # classic jupyter does not use metadata but allow additional fields
            # in content
            meta = metadata['content']['sos']
        else:
            # if there is no sos metadata, the execution should be started from a test suite
            # just ignore
            self._meta = {
                'workflow': '',
                'workflow_mode': False,
                'render_result': False,
                'capture_result': None,
                'cell_id': '0',
                'notebook_name': '',
                'notebook_path': '',
                'use_panel': False,
                'use_iopub': False,
                'default_kernel': self.kernel,
                'cell_kernel': self.kernel,
                'batch_mode': False,
                'suppress_error': False,
            }
            return self._meta

        env.log_to_file('KERNEL', f"Meta info: {meta}")
        self._meta = {
            'workflow':
                meta['workflow'] if 'workflow' in meta else '',
            'workflow_mode':
                False,
            'render_result':
                False,
            'capture_result':
                None,
            'cell_id':
                meta['cell_id'] if 'cell_id' in meta else '0',
            'notebook_path':
                meta['path'] if 'path' in meta else 'Untitled.ipynb',
            'use_panel':
                'use_panel' in meta and meta['use_panel'] is True,
            'use_iopub':
                'use_iopub' in meta and meta['use_iopub'] is True,
            'default_kernel':
                meta['default_kernel'] if 'default_kernel' in meta else 'SoS',
            'cell_kernel':
                meta['cell_kernel'] if 'cell_kernel' in meta else
                (meta['default_kernel'] if 'default_kernel' in meta else 'SoS'),
            'batch_mode':
                meta.get('batch_mode', False),
            'suppress_error':
                False,
        }
        # remove path and extension
        self._meta['notebook_name'] = os.path.basename(self._meta['notebook_path']).rsplit('.', 1)[0]
        if 'list_kernel' in meta and meta['list_kernel']:
            # https://github.com/jupyter/help/issues/153#issuecomment-289026056
            #
            # when the frontend is refreshed, cached comm would be lost and
            # communication would be discontinued. However, a kernel-list
            # request would be sent by the new-connection so we reset the
            # frontend_comm to re-connect to the frontend.
            self.comm_manager.register_target('sos_comm', self.sos_comm)
        return self._meta

    async def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=True):
        env.log_to_file('KERNEL', f'execute: {code}')
        if not self.controller:
            self.controller = start_controller(self)
        # load basic configuration each time in case user modifies the configuration during
        # runs. This is not very efficient but should not matter much during interactive
        # data analysis
        try:
            load_config_files()
        except Exception as e:
            self.warn(f'Failed to load configuration files: {e}')

        self._forward_input(allow_stdin)
        # switch to global default kernel
        try:
            if self.subkernels.find(self._meta['default_kernel']).name != self.subkernels.find(self.kernel).name:
                await self.switch_kernel(self._meta['default_kernel'])
                # evaluate user expression
        except Exception as e:
            return self.notify_error(e)
        # switch to cell kernel
        try:
            if self.subkernels.find(self._meta['cell_kernel']).name != self.subkernels.find(self.kernel).name:
                await self.switch_kernel(self._meta['cell_kernel'])
        except Exception as e:
            return self.notify_error(e)
        # execute with cell kernel
        try:
            ret = await self._do_execute(
                code=code,
                silent=silent,
                store_history=store_history,
                user_expressions=user_expressions,
                allow_stdin=allow_stdin)
        except Exception as e:
            return self.notify_error(e)
        if ret is None:
            ret = {'status': 'ok', 'payload': [], 'user_expressions': {}, 'execution_count': self._execution_count}

        out = {}
        for key, expr in (user_expressions or {}).items():
            try:
                # value = self.shell._format_user_obj(SoS_eval(expr))
                value = SoS_eval(expr)
                value = self.shell._format_user_obj(value)
            except Exception as e:
                self.warn(f'Failed to evaluate user expression {expr}: {e}')
                value = self.shell._user_obj_error()
            out[key] = value
        ret['user_expressions'] = out
        #
        if not silent and store_history:
            self._real_execution_count += 1
        self._execution_count = self._real_execution_count
        # make sure post_executed is triggered after the completion of all cell content
        self.shell.user_ns.update(env.sos_dict._dict)
        # trigger post processing of object and display matplotlib figures
        self.shell.events.trigger('post_execute')
        # tell the frontend the kernel for the "next" cell
        return ret

    async def _do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=True):
        # handles windows/unix newline
        code = '\n'.join(code.splitlines()) + '\n'
        if code == 'import os\n_pid = os.getpid()':
            # this is a special probing command from vim-ipython. Let us handle it specially
            # so that vim-python can get the pid.
            return
        for magic in self.magics.values():
            if magic.match(code):
                return await magic.apply(code, silent, store_history, user_expressions, allow_stdin)
        if self.kernel != 'SoS':
            # handle string interpolation before sending to the underlying kernel
            if self._meta['cell_id'] != '0' and not self._meta['batch_mode']:
                self.send_frontend_msg('cell-kernel', [self._meta['cell_id'], self.kernel])
            if code is None or not code.strip():
                return
            try:
                # We remove leading new line in case that users have a SoS
                # magic and a cell magic, separated by newline.
                # issue #58 and #33
                return await self.run_cell(code.lstrip(), silent, store_history)
            except KeyboardInterrupt:
                self.warn(
                    'KeyboardInterrupt. This will only be captured if the subkernel failed to process the signal.\n')
                return {'status': 'abort', 'execution_count': self._execution_count}
        else:
            # if the cell starts with comment, and newline, remove it
            lines = code.splitlines()
            empties = [x.startswith('#') or not x.strip() for x in lines]
            if not self._meta['batch_mode']:
                self.send_frontend_msg('cell-kernel', [self._meta['cell_id'], 'SoS'])
            if all(empties):
                return {'status': 'ok', 'payload': [], 'user_expressions': {}, 'execution_count': self._execution_count}
            idx = empties.index(False)
            if idx != 0 and (lines[idx].startswith('%') or lines[idx].startswith('!')):
                # not start from empty, but might have magic etc
                return await self._do_execute('\n'.join(lines[idx:]) + '\n', silent, store_history, user_expressions,
                                              allow_stdin)

            # if there is no more empty, magic etc, enter workflow mode
            # run sos
            try:
                self.run_sos_code(code, silent)
                return {'status': 'ok', 'payload': [], 'user_expressions': {}, 'execution_count': self._execution_count}
            except Exception as e:
                return self.notify_error(e)
            finally:
                # even if something goes wrong, we clear output so that the "preview"
                # will not be viewed by a later step.
                env.sos_dict.pop('input', None)
                env.sos_dict.pop('output', None)

    def do_shutdown(self, restart):
        #
        for name, (km, _) in self.kernels.items():
            try:
                km.shutdown_kernel(restart=restart)
            except Exception as e:
                self.warn(f'Failed to shutdown kernel {name}: {e}')

    def __del__(self):
        # upon releasing of sos kernel, kill all subkernels. This I thought would be
        # called by the Jupyter cleanup code or the OS (because subkernels are subprocesses)
        # but they are not.
        self.do_shutdown(False)


# there can only be one comm manager in a ipykernel process
_comm_lock = threading.Lock()
_comm_manager = None


def _get_comm_manager(*args, **kwargs):
    """Create a new CommManager."""
    global _comm_manager  # noqa
    if _comm_manager is None:
        with _comm_lock:
            if _comm_manager is None:
                _comm_manager = SoSCommManager(*args, **kwargs)
    return _comm_manager


comm.get_comm_manager = _get_comm_manager

if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp

    IPKernelApp.launch_instance(kernel_class=SoS_Kernel)
