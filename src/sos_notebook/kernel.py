#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import contextlib
import logging
import os
import subprocess
import sys
import time
from collections import OrderedDict, defaultdict
from textwrap import dedent

import pandas as pd
import pkg_resources
from ipykernel.ipkernel import IPythonKernel
from IPython.core.display import HTML

from IPython.utils.tokenutil import line_at_cursor, token_at_cursor
from jupyter_client import manager
from sos._version import __sos_version__, __version__
from sos.eval import SoS_eval, SoS_exec, interpolate
from sos.syntax import SOS_SECTION_HEADER
from sos.utils import format_duration, WorkflowDict, env, short_repr, load_config_files
from sos.targets import file_target

from ._version import __version__ as __notebook_version__
from .completer import SoS_Completer
from .inspector import SoS_Inspector
from .workflow_executor import (run_sos_workflow, execute_scratch_cell, NotebookLoggingHandler,
                                start_controller, stop_controller)
from .magics import SoS_Magics, Preview_Magic


class FlushableStringIO:
    def __init__(self, kernel, name, *args, **kwargs):
        self.kernel = kernel
        self.name = name

    def write(self, content):
        if content.startswith('HINT: '):
            content = content.splitlines()
            hint_line = content[0][6:].strip()
            content = '\n'.join(content[1:])
            self.kernel.send_response(self.kernel.iopub_socket, 'display_data',
                                      {
                                          'metadata': {},
                                          'data': {'text/html': HTML(
                                              f'<div class="sos_hint">{hint_line}</div>').data}
                                      })
        if content:
            if self.kernel._meta['capture_result'] is not None:
                self.kernel._meta['capture_result'].append(
                    ('stream', {'name': self.name, 'text': content}))
            self.kernel.send_response(self.kernel.iopub_socket, 'stream',
                                      {'name': self.name, 'text': content})

    def flush(self):
        pass


__all__ = ['SoS_Kernel']


class subkernel(object):
    # a class to information on subkernel
    def __init__(self, name=None, kernel=None, language='', color='', options={}):
        self.name = name
        self.kernel = kernel
        self.language = language
        self.color = color
        self.options = options

    def __repr__(self):
        return f'subkernel {self.name} with kernel {self.kernel} for language {self.language} with color {self.color}'


# translate a message to transient_display_data message


def make_transient_msg(msg_type, content):
    if msg_type == 'display_data':
        return {
            'data': content.get('data', {}),
            'metadata': content.get('metadata', {})
        }
    elif msg_type == 'stream':
        if content['name'] == 'stdout':
            return {
                'data': {
                    'text/plain': content['text'],
                    'application/vnd.jupyter.stdout': content['text']
                },
                'metadata': {}
            }
        else:
            return {
                'data': {
                    'text/plain': content['text'],
                    'application/vnd.jupyter.stderr': content['text']
                },
                'metadata': {}
            }
    else:
        raise ValueError(
            f"failed to translate message {msg_type} to transient_display_data message")


class Subkernels(object):
    # a collection of subkernels
    def __init__(self, kernel):
        self.sos_kernel = kernel
        self.language_info = kernel.supported_languages

        from jupyter_client.kernelspec import KernelSpecManager
        km = KernelSpecManager()
        specs = km.find_kernel_specs()
        # get supported languages
        self._kernel_list = []
        lan_map = {}
        for x in self.language_info.keys():
            for lname, knames in kernel.supported_languages[x].supported_kernels.items():
                for kname in knames:
                    if x != kname:
                        lan_map[kname] = (lname, self.get_background_color(self.language_info[x], lname),
                                          getattr(self.language_info[x], 'options', {}))
        # kernel_list has the following items
        #
        # 1. displayed name
        # 2. kernel name
        # 3. language name
        # 4. color
        for spec in specs.keys():
            if spec == 'sos':
                # the SoS kernel will be default theme color.
                self._kernel_list.append(
                    subkernel(name='SoS', kernel='sos', options={
                        'variable_pattern': r'^\s*[_A-Za-z0-9\.]+\s*$',
                        'assignment_pattern': r'^\s*([_A-Za-z0-9\.]+)\s*=.*$'}))
            elif spec in lan_map:
                # e.g. ir ==> R
                self._kernel_list.append(
                    subkernel(name=lan_map[spec][0], kernel=spec, language=lan_map[spec][0],
                              color=lan_map[spec][1], options=lan_map[spec][2]))
            else:
                # undefined language also use default theme color
                self._kernel_list.append(subkernel(name=spec, kernel=spec, language=km.get_kernel_spec(spec).language))

    def kernel_list(self):
        return self._kernel_list

    # now, no kernel is found, name has to be a new name and we need some definition
    # if kernel is defined
    def add_or_replace(self, kdef):
        for idx, x in enumerate(self._kernel_list):
            if x.name == kdef.name:
                self._kernel_list[idx] = kdef
                return self._kernel_list[idx]
            else:
                self._kernel_list.append(kdef)
                return self._kernel_list[-1]

    def get_background_color(self, plugin, lan):
        # if a single color is defined, it is used for all supported
        # languages
        if isinstance(plugin.background_color, str):
            # return the same background color for all inquiry
            return plugin.background_color
        else:
            # return color for specified, or any color if unknown inquiry is made
            return plugin.background_color.get(lan, next(iter(plugin.background_color.values())))

    def find(self, name, kernel=None, language=None, color=None, notify_frontend=True):
        # find from subkernel name
        def update_existing(idx):
            x = self._kernel_list[idx]
            if (kernel is not None and kernel != x.kernel) or (language not in (None, '', 'None') and language != x.language):
                raise ValueError(
                    f'Cannot change kernel or language of predefined subkernel {name} {x}')
            if color is not None:
                if color == 'default':
                    if self._kernel_list[idx].language:
                        self._kernel_list[idx].color = self.get_background_color(
                            self.language_info[self._kernel_list[idx].language], self._kernel_list[idx].language)
                    else:
                        self._kernel_list[idx].color = ''
                else:
                    self._kernel_list[idx].color = color
                if notify_frontend:
                    self.notify_frontend()

        # if the language module cannot be loaded for some reason
        if name in self.sos_kernel._failed_languages:
            raise self.sos_kernel._failed_languages[name]
        # find from language name (subkernel name, which is usually language name)
        for idx, x in enumerate(self._kernel_list):
            if x.name == name:
                if x.name == 'SoS' or x.language or language is None:
                    update_existing(idx)
                    return x
                else:
                    if not kernel:
                        kernel = name
                    break
        # find from kernel name
        for idx, x in enumerate(self._kernel_list):
            if x.kernel == name:
                # if exist language or no new language defined.
                if x.language or language is None:
                    update_existing(idx)
                    return x
                else:
                    # otherwise, try to use the new language
                    kernel = name
                    break

        if kernel is not None:
            # in this case kernel should have been defined in kernel list
            if kernel not in [x.kernel for x in self._kernel_list]:
                raise ValueError(
                    f'Unrecognized Jupyter kernel name {kernel}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"')
            # now this a new instance for an existing kernel
            kdef = [x for x in self._kernel_list if x.kernel == kernel][0]
            if not language:
                if color == 'default':
                    if kdef.language:
                        color = self.get_background_color(
                            self.language_info[kdef.language], kdef.language)
                    else:
                        color = kdef.color
                new_def = self.add_or_replace(subkernel(name, kdef.kernel, kdef.language, kdef.color if color is None else color,
                                                        getattr(self.language_info[kdef.language], 'options', {}) if kdef.language else {}))
                if notify_frontend:
                    self.notify_frontend()
                return new_def
            else:
                # if language is defined,
                if ':' in language:
                    # if this is a new module, let us create an entry point and load
                    from pkg_resources import EntryPoint
                    mn, attr = language.split(':', 1)
                    ep = EntryPoint(name=kernel, module_name=mn,
                                    attrs=tuple(attr.split('.')))
                    try:
                        plugin = ep.resolve()
                        self.language_info[name] = plugin
                        # for convenience, we create two entries for, e.g. R and ir
                        # but only if there is no existing definition
                        for supported_lan, supported_kernels in plugin.supported_kernels.items():
                            for supported_kernel in supported_kernels:
                                if name != supported_kernel and supported_kernel not in self.language_info:
                                    self.language_info[supported_kernel] = plugin
                            if supported_lan not in self.language_info:
                                self.language_info[supported_lan] = plugin
                    except Exception as e:
                        raise RuntimeError(
                            f'Failed to load language {language}: {e}')
                    #
                    if color == 'default':
                        color = self.get_background_color(plugin, kernel)
                    new_def = self.add_or_replace(subkernel(name, kdef.kernel, kernel, kdef.color if color is None else color,
                                                            getattr(plugin, 'options', {})))
                else:
                    # if should be defined ...
                    if language not in self.language_info:
                        raise RuntimeError(
                            f'Unrecognized language definition {language}, which should be a known language name or a class in the format of package.module:class')
                    #
                    self.language_info[name] = self.language_info[language]
                    if color == 'default':
                        color = self.get_background_color(
                            self.language_info[name], language)
                    new_def = self.add_or_replace(subkernel(name, kdef.kernel, language, kdef.color if color is None else color,
                                                            getattr(self.language_info[name], 'options', {})))
                if notify_frontend:
                    self.notify_frontend()
                return new_def
        elif language is not None:
            # kernel is not defined and we only have language
            if ':' in language:
                # if this is a new module, let us create an entry point and load
                from pkg_resources import EntryPoint
                mn, attr = language.split(':', 1)
                ep = EntryPoint(name='__unknown__', module_name=mn,
                                attrs=tuple(attr.split('.')))
                try:
                    plugin = ep.resolve()
                    self.language_info[name] = plugin
                except Exception as e:
                    raise RuntimeError(
                        f'Failed to load language {language}: {e}')
                if name in plugin.supported_kernels:
                    # if name is defined in the module, only search kernels for this language
                    avail_kernels = [x for x in plugin.supported_kernels[name] if
                                     x in [y.kernel for y in self._kernel_list]]
                else:
                    # otherwise we search all supported kernels
                    avail_kernels = [x for x in sum(plugin.supported_kernels.values(), []) if
                                     x in [y.kernel for y in self._kernel_list]]

                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'.format(
                            ', '.join(sum(plugin.supported_kernels.values(), [])), language))
                # use the first available kernel
                # find the language that has the kernel
                lan_name = list({x: y for x, y in plugin.supported_kernels.items(
                ) if avail_kernels[0] in y}.keys())[0]
                if color == 'default':
                    color = self.get_background_color(plugin, lan_name)
                new_def = self.add_or_replace(subkernel(name, avail_kernels[0], lan_name, self.get_background_color(plugin, lan_name) if color is None else color,
                                                        getattr(plugin, 'options', {})))
            else:
                # if a language name is specified (not a path to module), if should be defined in setup.py
                if language not in self.language_info:
                    raise RuntimeError(
                        f'Unrecognized language definition {language}')
                #
                plugin = self.language_info[language]
                if language in plugin.supported_kernels:
                    avail_kernels = [x for x in plugin.supported_kernels[language] if
                                     x in [y.kernel for y in self._kernel_list]]
                else:
                    avail_kernels = [x for x in sum(plugin.supported_kernels.values(), []) if
                                     x in [y.kernel for y in self._kernel_list]]
                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'.format(
                            ', '.join(
                                sum(self.language_info[language].supported_kernels.values(), [])),
                            language))

                new_def = self.add_or_replace(subkernel(
                    name, avail_kernels[0], language,
                    self.get_background_color(
                        self.language_info[language], language) if color is None or color == 'default' else color,
                    getattr(self.language_info[language], 'options', {})))

            self.notify_frontend()
            return new_def
        else:
            # let us check if there is something wrong with the pre-defined language
            for entrypoint in pkg_resources.iter_entry_points(group='sos_languages'):
                if entrypoint.name == name:
                    # there must be something wrong, let us trigger the exception here
                    entrypoint.load()
            # if nothing is triggerred, kernel is not defined, return a general message
            raise ValueError(
                f'No subkernel named {name} is found. Please make sure that you have the kernel installed (listed in the output of "jupyter kernelspec list" and usable in jupyter by itself), install appropriate language module (e.g. "pip install sos-r"), restart jupyter notebook and try again.')

    def update(self, notebook_kernel_list):
        for kinfo in notebook_kernel_list:
            try:
                # if we can find the kernel, fine...
                self.find(kinfo[0], kinfo[1], kinfo[2],
                          kinfo[3], notify_frontend=False)
            except Exception as e:
                # otherwise do not worry about it.
                env.logger.warning(
                    f'Failed to locate subkernel {kinfo[0]} with kernerl "{kinfo[1]}" and language "{kinfo[2]}": {e}')

    def notify_frontend(self):
        self._kernel_list.sort(key=lambda x: x.name)
        self.sos_kernel.send_frontend_msg('kernel-list',
                                          [[x.name, x.kernel, x.language, x.color, x.options] for x in self._kernel_list])


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
            try:
                plugin = entrypoint.load()
                self._supported_languages[name] = plugin
            except Exception as e:
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
        super(SoS_Kernel, self).__init__(**kwargs)
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
        self.kernels = {}
        # self.shell = InteractiveShell.instance()
        self.format_obj = self.shell.display_formatter.format

        self.original_keys = None
        self._meta = {'use_panel': True}
        self._supported_languages = None
        self._completer = None
        self._inspector = None
        self._real_execution_count = 1
        self._execution_count = 1
        self._debug_mode = False
        self.frontend_comm = None
        self.comm_manager.register_target('sos_comm', self.sos_comm)
        self.my_tasks = {}
        self.magics = SoS_Magics(self)
        self.last_executed_code = ''
        self._kernel_return_vars = []
        self._failed_languages = {}
        # enable matplotlib by default #77
        self.shell.enable_gui = lambda gui: None
        # sos does not yet support MaxOSX backend to start a new window
        # so a default inline mode is used.
        self.shell.enable_matplotlib('inline')
        #
        self.editor_kernel = 'sos'
        # remove all other ahdnlers
        env.logger.handlers = []
        env.logger.addHandler(
            NotebookLoggingHandler({
                0: logging.ERROR,
                1: logging.WARNING,
                2: logging.INFO,
                3: logging.DEBUG,
                4: logging.TRACE,
                None: logging.INFO
            }[env.verbosity], kernel=self))
        env.logger.print = lambda cell_id, msg, *args: \
            self.send_frontend_msg('print', [cell_id, msg])
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
                elif k == 'kill-task':
                    # kill specified task
                    from sos.hosts import Host
                    Host(v[1])._task_engine.kill_tasks([v[0]])
                    self.send_frontend_msg('task_status',
                                           {
                                               'task_id': v[0],
                                               'queue': v[1],
                                               'status': 'abort'
                                           })
                elif k == 'cancel-workflow':
                    from .workflow_executor import cancel_workflow
                    cancel_workflow(v[0], self)
                elif k == 'execute-workflow':
                    from .workflow_executor import execute_pending_workflow
                    execute_pending_workflow(v, self)
                elif k == 'resume-task':
                    # kill specified task
                    from sos.hosts import Host
                    Host(v[1])._task_engine.resume_task(v[0])
                    self.send_frontend_msg('task_status',
                                           {
                                               'task_id': v[0],
                                               'queue': v[1],
                                               'status': 'pending'
                                           })
                elif k == 'task-info':
                    self._meta['use_panel'] = True
                    from sos.hosts import Host
                    task_queue = v[1]
                    task_id = v[0]
                    host = Host(task_queue)
                    result = host._task_engine.query_tasks(
                        [task_id], verbosity=2, html=True)
                    # log_to_file(result)
                    self.send_frontend_msg('display_data', {
                        'metadata': {},
                        'data': {'text/plain': result,
                                 'text/html': HTML(result).data
                                 }})

                    # now, there is a possibility that the status of the task is different from what
                    # task engine knows (e.g. a task is rerun outside of jupyter). In this case, since we
                    # already get the status, we should update the task engine...
                    #
                    # <tr><th align="right"  width="30%">Status</th><td align="left"><div class="one_liner">completed</div></td></tr>
                    status = result.split(
                        '>Status<', 1)[-1].split('</div', 1)[0].split('>')[-1]
                    host._task_engine.update_task_status(task_id, status)
                elif k == 'update-task-status':
                    if not isinstance(v, list):
                        continue
                    # split by host ...
                    host_status = defaultdict(list)
                    for name in v:
                        try:
                            tqu, tid = rsplit('_', 1)
                        except Exception:
                            # incorrect ID...
                            continue
                        host_status[tqu].append(tid)
                    # log_to_file(host_status)
                    #
                    from sos.hosts import Host
                    for tqu, tids in host_status.items():
                        try:
                            h = Host(tqu)
                        except Exception:
                            continue
                        for tid, tst, tdt in h._task_engine.monitor_tasks(tids):
                            self.send_frontend_msg('task_status',
                                                   {
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
                        if self._debug_mode:
                            env.log_to_file(tbl)
                    except Exception as e:
                        self.send_frontend_msg(
                            'alert', f'Failed to paste clipboard as table: {e}')
                elif k == 'notebook-version':
                    # send the version of notebook, right now we will not do anything to it, but
                    # we will send the version of sos-notebook there
                    self.send_frontend_msg(
                        'notebook-version', __notebook_version__)
                else:
                    # this somehow does not work
                    self.warn(f'Unknown message {k}: {v}')

    def send_frontend_msg(self, msg_type, msg=None):
        # if comm is never created by frontend, the kernel is in test mode without frontend
        if msg_type in ('display_data', 'stream'):
            if self._meta['use_panel'] is False:
                if msg_type in ('display_data', 'stream'):
                    self.send_response(self.iopub_socket, msg_type,
                                       {} if msg is None else msg)
            else:
                self.frontend_comm.send(
                    make_transient_msg(
                        msg_type, msg),
                    {'msg_type': 'transient_display_data'})
        elif self.frontend_comm:
            self.frontend_comm.send({} if msg is None else msg, {
                                    'msg_type': msg_type})
        elif self._debug_mode:
            # we should not always do this because the kernel could be triggered by
            # tests, which will not have a frontend sos comm
            self.warn(
                'Frontend communicator is broken. Please restart jupyter server')

    def _reset_dict(self):
        env.sos_dict = WorkflowDict()
        SoS_exec('import os, sys, glob', None)
        SoS_exec('from sos.runtime import *', None)
        SoS_exec("run_mode = 'interactive'", None)
        self.original_keys = set(env.sos_dict._dict.keys()) | {'SOS_VERSION', 'CONFIG',
                                                               'step_name', '__builtins__', 'input', 'output',
                                                               'depends'}

    @contextlib.contextmanager
    def redirect_sos_io(self):
        save_stdout = sys.stdout
        save_stderr = sys.stderr
        sys.stdout = FlushableStringIO(self, 'stdout')
        sys.stderr = FlushableStringIO(self, 'stderr')
        yield
        sys.stdout = save_stdout
        sys.stderr = save_stderr

    def get_vars_from(self, items, from_kernel=None, explicit=False):
        if from_kernel is None or from_kernel.lower() == 'sos':
            # autmatically get all variables with names start with 'sos'
            default_items = [x for x in env.sos_dict.keys() if x.startswith(
                'sos') and x not in self.original_keys]
            items = default_items if not items else items + default_items
            for item in items:
                if item not in env.sos_dict:
                    self.warn(f'Variable {item} does not exist')
                    return
            if not items:
                return
            if self.kernel in self.supported_languages:
                lan = self.supported_languages[self.kernel]
                kinfo = self.subkernels.find(self.kernel)
                try:
                    lan(self, kinfo.kernel).get_vars(items)
                except Exception as e:
                    self.warn(f'Failed to get variable: {e}\n')
                    return
            elif self.kernel == 'SoS':
                self.warn(
                    'Magic %get without option --kernel can only be executed by subkernels')
                return
            else:
                if explicit:
                    self.warn(
                        f'Magic %get failed because the language module for {self.kernel} is not properly installed. Please install it according to language specific instructions on the Running SoS section of the SoS homepage and restart Jupyter server.')
                return
        elif self.kernel.lower() == 'sos':
            # if another kernel is specified and the current kernel is sos
            # we get from subkernel
            try:
                self.switch_kernel(from_kernel)
                self.put_vars_to(items)
            except Exception as e:
                self.warn(
                    f'Failed to get {", ".join(items)} from {from_kernel}: {e}')
            finally:
                self.switch_kernel('SoS')
        else:
            # if another kernel is specified, we should try to let that kernel pass
            # the variables to this one directly
            try:
                my_kernel = self.kernel
                self.switch_kernel(from_kernel)
                # put stuff to sos or my_kernel directly
                self.put_vars_to(
                    items, to_kernel=my_kernel, explicit=explicit)
            except Exception as e:
                self.warn(
                    f'Failed to get {", ".join(items)} from {from_kernel}: {e}')
            finally:
                # then switch back
                self.switch_kernel(my_kernel)

    def put_vars_to(self, items, to_kernel=None, explicit=False):
        if self.kernel.lower() == 'sos':
            if to_kernel is None:
                self.warn(
                    'Magic %put without option --kernel can only be executed by subkernels')
                return
            # if another kernel is specified and the current kernel is sos
            try:
                # switch to kernel and bring in items
                self.switch_kernel(to_kernel, in_vars=items)
            except Exception as e:
                self.warn(
                    f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
            finally:
                # switch back
                self.switch_kernel('SoS')
        else:
            # put to sos kernel or another kernel
            #
            # items can be None if unspecified
            if not items:
                # we do not simply return because we need to return default variables (with name startswith sos
                items = []
            if self.kernel not in self.supported_languages:
                if explicit:
                    self.warn(
                        f'Subkernel {self.kernel} does not support magic %put.')
                return
            #
            lan = self.supported_languages[self.kernel]
            kinfo = self.subkernels.find(self.kernel)
            # pass language name to to_kernel
            try:
                if to_kernel:
                    objects = lan(self, kinfo.kernel).put_vars(
                        items, to_kernel=self.subkernels.find(to_kernel).language)
                else:
                    objects = lan(self, kinfo.kernel).put_vars(
                        items, to_kernel='SoS')
            except Exception as e:
                # if somethign goes wrong in the subkernel does not matter
                if self._debug_mode:
                    self.warn(
                        f'Failed to call put_var({items}) from {kinfo.kernel}')
                objects = {}
            if isinstance(objects, dict):
                # returns a SOS dictionary
                try:
                    env.sos_dict.update(objects)
                except Exception as e:
                    self.warn(
                        f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                    return

                if to_kernel is None:
                    return
                # if another kernel is specified and the current kernel is not sos
                # we need to first put to sos then to another kernel
                try:
                    my_kernel = self.kernel
                    # switch to the destination kernel and bring in vars
                    self.switch_kernel(to_kernel, in_vars=items)
                except Exception as e:
                    self.warn(
                        f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                finally:
                    # switch back to the original kernel
                    self.switch_kernel(my_kernel)
            elif isinstance(objects, str):
                # an statement that will be executed in the destination kernel
                if to_kernel is None or to_kernel == 'SoS':
                    # evaluate in SoS, this should not happen or rarely happen
                    # because the subkernel should return a dictionary for SoS kernel
                    try:
                        exec(objects, env.sos_dict._dict)
                    except Exception as e:
                        self.warn(
                            f'Failed to put variables {items} to SoS kernel: {e}')
                        return
                try:
                    my_kernel = self.kernel
                    # switch to the destination kernel
                    self.switch_kernel(to_kernel)
                    # execute the statement to pass variables directly to destination kernel
                    self.run_cell(objects, True, False)
                except Exception as e:
                    self.warn(
                        f'Failed to put {", ".join(items)} to {to_kernel}: {e}')
                finally:
                    # switch back to the original kernel
                    self.switch_kernel(my_kernel)
            else:
                self.warn(
                    f'Unrecognized return value of type {object.__class__.__name__} for action %put')
                return

    def do_is_complete(self, code):
        '''check if new line is in order'''
        code = code.strip()
        if not code:
            return {'status': 'complete', 'indent': ''}
        if any(code.startswith(x) for x in ['%dict', '%paste', '%edit', '%cd', '!']):
            return {'status': 'complete', 'indent': ''}
        if code.endswith(':') or code.endswith(','):
            return {'status': 'incomplete', 'indent': '  '}
        lines = code.split('\n')
        if lines[-1].startswith(' ') or lines[-1].startswith('\t'):
            # if it is a new line, complte
            empty = [idx for idx, x in enumerate(
                lines[-1]) if x not in (' ', '\t')][0]
            return {'status': 'incomplete', 'indent': lines[-1][:empty]}
        #
        if SOS_SECTION_HEADER.match(lines[-1]):
            return {'status': 'incomplete', 'indent': ''}
        #
        return {'status': 'incomplete', 'indent': ''}

    def do_inspect(self, code, cursor_pos, detail_level=0):
        if self.editor_kernel.lower() == 'sos':
            line, offset = line_at_cursor(code, cursor_pos)
            name = token_at_cursor(code, cursor_pos)
            data = self.inspector.inspect(name, line, cursor_pos - offset)
            return {
                'status': 'ok',
                'metadata': {},
                'found': True if data else False,
                'data': data
            }
        else:
            cell_kernel = self.subkernels.find(self.editor_kernel)
            try:
                _, KC = self.kernels[cell_kernel.name]
            except Exception as e:
                if self._debug_mode:
                    env.log_to_file(
                        f'Failed to get subkernels {cell_kernel.name}')
                KC = self.KC
            try:
                KC.inspect(code, cursor_pos)
                while KC.shell_channel.msg_ready():
                    msg = KC.shell_channel.get_msg()
                    if msg['header']['msg_type'] == 'inspect_reply':
                        return msg['content']
                    else:
                        # other messages, do not know what is going on but
                        # we should not wait forever and cause a deadloop here
                        if self._debug_mode:
                            env.log_to_file(
                                f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead")
                        break
            except Exception as e:
                if self._debug_mode:
                    env.log_to_file(f'Completion fail with exception: {e}')

    def do_complete(self, code, cursor_pos):
        if self.editor_kernel.lower() == 'sos':
            text, matches = self.completer.complete_text(code, cursor_pos)
            return {'matches': matches,
                    'cursor_end': cursor_pos,
                    'cursor_start': cursor_pos - len(text),
                    'metadata': {},
                    'status': 'ok'}
        else:
            cell_kernel = self.subkernels.find(self.editor_kernel)
            try:
                _, KC = self.kernels[cell_kernel.name]
            except Exception as e:
                if self._debug_mode:
                    env.log_to_file(
                        f'Failed to get subkernels {cell_kernel.name}')
                KC = self.KC
            try:
                KC.complete(code, cursor_pos)
                while KC.shell_channel.msg_ready():
                    msg = KC.shell_channel.get_msg()
                    if msg['header']['msg_type'] == 'complete_reply':
                        return msg['content']
                    else:
                        # other messages, do not know what is going on but
                        # we should not wait forever and cause a deadloop here
                        if self._debug_mode:
                            env.log_to_file(
                                f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead")
                        break
            except Exception as e:
                if self._debug_mode:
                    env.log_to_file(f'Completion fail with exception: {e}')

    def warn(self, message):
        message = str(message).rstrip() + '\n'
        if message.strip():
            self.send_response(self.iopub_socket, 'stream',
                               {'name': 'stderr', 'text': message})

    def run_cell(self, code, silent, store_history, on_error=None):
        #
        if not self.KM.is_alive():
            self.send_response(self.iopub_socket, 'stream',
                               dict(name='stdout', text='Restarting kernel "{}"\n'.format(self.kernel)))
            self.KM.restart_kernel(now=False)
            self.KC = self.KM.client()
        # flush stale replies, which could have been ignored, due to missed heartbeats
        while self.KC.shell_channel.msg_ready():
            self.KC.shell_channel.get_msg()
        # executing code in another kernel
        self.KC.execute(code, silent=silent, store_history=store_history)

        # first thing is wait for any side effects (output, stdin, etc.)
        _execution_state = "busy"
        while _execution_state != 'idle':
            # display intermediate print statements, etc.
            while self.KC.stdin_channel.msg_ready():
                sub_msg = self.KC.stdin_channel.get_msg()
                if self._debug_mode:
                    env.log_to_file(
                        f"MSG TYPE {sub_msg['header']['msg_type']}")
                    env.log_to_file(f'CONTENT  {sub_msg}')
                if sub_msg['header']['msg_type'] != 'input_request':
                    self.send_response(
                        self.stdin_socket, sub_msg['header']['msg_type'], sub_msg["content"])
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
                if self._debug_mode:
                    env.log_to_file(f'MSG TYPE {msg_type}')
                    env.log_to_file(f'CONTENT  {sub_msg["content"]}')
                if msg_type == 'status':
                    _execution_state = sub_msg["content"]["execution_state"]
                else:
                    if msg_type in ('execute_input', 'execute_result'):
                        # override execution count with the master count,
                        # not sure if it is needed
                        sub_msg['content']['execution_count'] = self._execution_count
                    #
                    if msg_type in ['display_data', 'stream', 'execute_result', 'update_display_data']:
                        if self._meta['capture_result'] is not None:
                            self._meta['capture_result'].append(
                                (msg_type, sub_msg['content']))
                        if silent:
                            continue
                    self.send_response(
                        self.iopub_socket, msg_type, sub_msg['content'])
        #
        # now get the real result
        reply = self.KC.get_shell_msg(timeout=10)
        reply['content']['execution_count'] = self._execution_count
        return reply['content']

    def switch_kernel(self, kernel, in_vars=None, ret_vars=None, kernel_name=None, language=None, color=None):
        # switching to a non-sos kernel
        if not kernel:
            kinfo = self.subkernels.find(self.kernel)
            self.send_response(self.iopub_socket, 'stream',
                               dict(name='stdout', text='''\
Active subkernels: {}
Available subkernels:\n{}'''.format(', '.join(self.kernels.keys()),
                                    '\n'.join(['    {} ({})'.format(x.name, x.kernel) for x in self.subkernels.kernel_list()]))))
            return
        kinfo = self.subkernels.find(kernel, kernel_name, language, color)
        if kinfo.name == self.kernel:
            # the same kernel, do nothing?
            # but the senario can be
            #
            # kernel in SoS
            # cell R
            # %use R -i n
            #
            # SoS get:
            #
            # %softwidth --default-kernel R --cell-kernel R
            # %use R -i n
            #
            # Now, SoS -> R without variable passing
            # R -> R should honor -i n

            # or, when we randomly jump cells, we should more aggreessively return
            # automatically shared variables to sos (done by the following) (#375)
            if kinfo.name != 'SoS':
                self.switch_kernel('SoS')
                self.switch_kernel(kinfo.name, in_vars, ret_vars)
        elif kinfo.name == 'SoS':
            self.put_vars_to(self._kernel_return_vars)
            self._kernel_return_vars = []
            self.kernel = 'SoS'
        elif self.kernel != 'SoS':
            # not to 'sos' (kernel != 'sos'), see if they are the same kernel under
            self.switch_kernel('SoS', in_vars, ret_vars)
            self.switch_kernel(kinfo.name, in_vars, ret_vars)
        else:
            if self._debug_mode:
                self.warn(f'Switch from {self.kernel} to {kinfo.name}')
            # case when self.kernel == 'sos', kernel != 'sos'
            # to a subkernel
            new_kernel = False
            if kinfo.name not in self.kernels:
                # start a new kernel
                try:
                    self.kernels[kinfo.name] = manager.start_new_kernel(
                        startup_timeout=60, kernel_name=kinfo.kernel, cwd=os.getcwd())
                    new_kernel = True
                except Exception as e:
                    # try toget error message
                    import tempfile
                    with tempfile.TemporaryFile() as ferr:
                        try:
                            # this should fail
                            manager.start_new_kernel(
                                startup_timeout=60, kernel_name=kinfo.kernel, cwd=os.getcwd(),
                                stdout=subprocess.DEVNULL, stderr=ferr)
                        except:
                            ferr.seek(0)
                            self.warn(
                                f'Failed to start kernel "{kernel}". {e}\nError Message:\n{ferr.read().decode()}')
                    return
            self.KM, self.KC = self.kernels[kinfo.name]
            self._kernel_return_vars = [] if ret_vars is None else ret_vars
            self.kernel = kinfo.name
            if new_kernel and self.kernel in self.supported_languages:
                init_stmts = self.supported_languages[self.kernel](
                    self, kinfo.kernel).init_statements
                if init_stmts:
                    self.run_cell(init_stmts, True, False)
            # passing
            self.get_vars_from(in_vars)

    def shutdown_kernel(self, kernel, restart=False):
        kernel = self.subkernels.find(kernel).name
        if kernel == 'SoS':
            # cannot restart myself ...
            self.warn('Cannot restart SoS kernel from within SoS.')
        elif kernel:
            if kernel not in self.kernels:
                self.send_response(self.iopub_socket, 'stream',
                                   dict(name='stdout', text=f'{kernel} is not running'))
            elif restart:
                orig_kernel = self.kernel
                try:
                    # shutdown
                    self.shutdown_kernel(kernel)
                    # switch back to kernel (start a new one)
                    self.switch_kernel(kernel)
                finally:
                    # finally switch to starting kernel
                    self.switch_kernel(orig_kernel)
            else:
                # shutdown
                if self.kernel == kernel:
                    self.switch_kernel('SoS')
                try:
                    self.kernels[kernel][0].shutdown_kernel(restart=False)
                except Exception as e:
                    self.warn(f'Failed to shutdown kernel {kernel}: {e}\n')
                finally:
                    self.kernels.pop(kernel)
        else:
            self.send_response(self.iopub_socket, 'stream',
                               dict(name='stdout', text='Specify one of the kernels to shutdown: SoS{}\n'
                                    .format(''.join(f', {x}' for x in self.kernels))))
        stop_controller(self.controller)

    def get_response(self, statement, msg_types, name=None):
        # get response of statement of specific msg types.
        responses = []
        self.KC.execute(statement, silent=False, store_history=False)
        # first thing is wait for any side effects (output, stdin, etc.)
        _execution_state = "busy"
        while _execution_state != 'idle':
            # display intermediate print statements, etc.
            while self.KC.iopub_channel.msg_ready():
                sub_msg = self.KC.iopub_channel.get_msg()
                msg_type = sub_msg['header']['msg_type']
                if self._debug_mode:
                    env.log_to_file(
                        f'Received {msg_type} {sub_msg["content"]}')
                if msg_type == 'status':
                    _execution_state = sub_msg["content"]["execution_state"]
                else:
                    if msg_type in msg_types and (name is None or sub_msg['content'].get('name', None) in name):
                        if self._debug_mode:
                            env.log_to_file(
                                f'Capture response: {msg_type}: {sub_msg["content"]}')
                        responses.append([msg_type, sub_msg['content']])
                    else:
                        if self._debug_mode:
                            env.log_to_file(
                                f'Non-response: {msg_type}: {sub_msg["content"]}')
                        self.send_response(
                            self.iopub_socket, msg_type, sub_msg['content'])
        if not responses and self._debug_mode:
            self.warn(
                f'Failed to get a response from message type {msg_types} for the execution of {statement}')
        return responses

    def run_sos_code(self, code, silent):
        code = dedent(code)
        with self.redirect_sos_io():
            try:
                if self._workflow_mode:
                    res = run_sos_workflow(
                        code=code, raw_args=self.options, kernel=self)
                else:
                    res = execute_scratch_cell(code=code, raw_args=self.options,
                                               kernel=self)
                self.send_result(res, silent)
            except Exception as e:
                sys.stderr.flush()
                sys.stdout.flush()
                # self.send_response(self.iopub_socket, 'display_data',
                #    {
                #        'metadata': {},
                #        'data': { 'text/html': HTML('<hr color="black" width="60%">').data}
                #    })
                raise
            except KeyboardInterrupt:
                self.warn('Keyboard Interrupt\n')
                return {'status': 'abort', 'execution_count': self._execution_count}
            finally:
                sys.stderr.flush()
                sys.stdout.flush()
        #
        if not silent:
            input_files = [str(x) for x in env.sos_dict.get('step_input', []) if isinstance(x, file_target)]
            output_files = [str(x) for x in env.sos_dict.get('step_output', []) if isinstance(x, file_target)]

            # use a table to list input and/or output file if exist
            if output_files and not (hasattr(self, '_no_auto_preview') and self._no_auto_preview):
                title = f'%preview {" ".join(output_files)}'
                if not self._meta['use_panel']:
                    self.send_response(self.iopub_socket, 'display_data', {
                        'metadata': {},
                        'data': {'text/html': HTML(f'<div class="sos_hint">{title}</div>').data}
                    })

                if hasattr(self, 'in_sandbox') and self.in_sandbox:
                    # if in sand box, do not link output to their files because these
                    # files will be removed soon.
                    self.send_frontend_msg('display_data', {
                        'metadata': {},
                        'data': {'text/html':
                            '''<div class="sos_hint"> input: {}<br>output: {}\n</div>'''.format(
                                 ', '.join(x for x in input_files),
                                ', '.join(x for x in output_files))
                        }
                    })
                else:
                    self.send_frontend_msg('display_data', {
                        'metadata': {},
                        'data': {
                        'text/html':
                            '''<div class="sos_hint"> input: {}<br>output: {}\n</div>'''.format(
                                 ', '.join(
                                     f'<a target="_blank" href="{x}">{x}</a>' for x in input_files),
                                 ', '.join(
                                     f'<a target="_blank" href="{x}">{x}</a>' for x in output_files))
                        }
                    })

                Preview_Magic(self).handle_magic_preview(output_files, "SoS",
                                                         title=f'%preview {" ".join(output_files)}')

    def render_result(self, res):
        if not self._meta['render_result']:
            return res
        if not isinstance(res, str):
            self.warn(
                f'Cannot render result {short_repr(res)} in type {res.__class__.__name__} as {self._meta["render_result"]}.')
        else:
            # import the object from IPython.display
            mod = __import__('IPython.display')
            if not hasattr(mod.display, self._meta['render_result']):
                self.warn(
                    f'Unrecognized render format {self._meta["render_result"]}')
            else:
                func = getattr(mod.display, self._meta['render_result'])
                res = func(res)
        return res

    def send_result(self, res, silent=False):
        # this is Ok, send result back
        if not silent and res is not None:
            format_dict, md_dict = self.format_obj(self.render_result(res))
            self.send_response(self.iopub_socket, 'execute_result',
                               {'execution_count': self._execution_count, 'data': format_dict,
                                'metadata': md_dict})

    def init_metadata(self, metadata):
        super(SoS_Kernel, self).init_metadata(metadata)
        if 'sos' in metadata['content']:
            meta = metadata['content']['sos']
        else:
            # if there is no sos metadata, the execution should be started from a test suite
            # just ignore
            self._meta = {
                'workflow': '',
                'workflow_mode': False,
                'render_result': False,
                'capture_result': None,
                'cell_id': 0,
                'notebook_name': '',
                'notebook_path': '',
                'use_panel': False,
                'default_kernel': self.kernel,
                'cell_kernel': self.kernel,
                'toc': '',
                'batch_mode': False
            }
            return self._meta

        if self._debug_mode:
            self.warn(f"Meta info: {meta}")
        self._meta = {
            'workflow': meta['workflow'] if 'workflow' in meta else '',
            'workflow_mode': False,
            'render_result': False,
            'capture_result': None,
            'cell_id': meta['cell_id'] if 'cell_id' in meta else "",
            'notebook_path': meta['path'] if 'path' in meta else 'Untitled.ipynb',
            'use_panel': True if 'use_panel' in meta and meta['use_panel'] is True else False,
            'default_kernel': meta['default_kernel'] if 'default_kernel' in meta else 'SoS',
            'cell_kernel': meta['cell_kernel'] if 'cell_kernel' in meta else (meta['default_kernel'] if 'default_kernel' in meta else 'SoS'),
            'toc': meta.get('toc', ''),
            'batch_mode': meta.get('batch_mode', False)
        }
        # remove path and extension
        self._meta['notebook_name'] = os.path.basename(
            self._meta['notebook_path']).rsplit('.', 1)[0]
        if 'list_kernel' in meta and meta['list_kernel']:
            # https://github.com/jupyter/help/issues/153#issuecomment-289026056
            #
            # when the frontend is refreshed, cached comm would be lost and
            # communication would be discontinued. However, a kernel-list
            # request would be sent by the new-connection so we reset the
            # frontend_comm to re-connect to the frontend.
            self.comm_manager.register_target('sos_comm', self.sos_comm)
        return self._meta

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=True):
        if self._debug_mode:
            self.warn(code)
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
                self.switch_kernel(self._meta['default_kernel'])
                # evaluate user expression
        except Exception as e:
            self.warn(
                f'Failed to switch to language {self._meta["default_kernel"]}: {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self._execution_count,
                    }
        # switch to cell kernel
        try:
            if self.subkernels.find(self._meta['cell_kernel']).name != self.subkernels.find(self.kernel).name:
                self.switch_kernel(self._meta['cell_kernel'])
        except Exception as e:
            self.warn(
                f'Failed to switch to language {self._meta["cell_kernel"]}: {e}\n')
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self._execution_count,
                    }
        # execute with cell kernel
        try:
            ret = self._do_execute(code=code, silent=silent, store_history=store_history,
                                   user_expressions=user_expressions, allow_stdin=allow_stdin)
        except Exception as e:
            self.warn(e)
            return {'status': 'error',
                    'ename': e.__class__.__name__,
                    'evalue': str(e),
                    'traceback': [],
                    'execution_count': self._execution_count,
                    }

        if ret is None:
            ret = {'status': 'ok',
                   'payload': [], 'user_expressions': {},
                   'execution_count': self._execution_count}

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

    def _do_execute(self, code, silent, store_history=True, user_expressions=None,
                    allow_stdin=True):
        # handles windows/unix newline
        code = '\n'.join(code.splitlines()) + '\n'

        if self.original_keys is None:
            self._reset_dict()
        if code == 'import os\n_pid = os.getpid()':
            # this is a special probing command from vim-ipython. Let us handle it specially
            # so that vim-python can get the pid.
            return
        for magic in self.magics.values():
            if magic.match(code):
                return magic.apply(code, silent, store_history, user_expressions, allow_stdin)
        if self.kernel != 'SoS':
            # handle string interpolation before sending to the underlying kernel
            if code:
                self.last_executed_code = code
            if self._meta['cell_id']:
                self.send_frontend_msg(
                    'cell-kernel', [self._meta['cell_id'], self.kernel])
                self._meta['cell_id'] = ""
            if code is None:
                return
            try:
                # We remove leading new line in case that users have a SoS
                # magic and a cell magic, separated by newline.
                # issue #58 and #33
                return self.run_cell(code.lstrip(), silent, store_history)
            except KeyboardInterrupt:
                self.warn('Keyboard Interrupt\n')
                self.KM.interrupt_kernel()
                return {'status': 'abort', 'execution_count': self._execution_count}
        else:
            if code:
                self.last_executed_code = code

            # if the cell starts with comment, and newline, remove it
            lines = code.splitlines()
            empties = [x.startswith('#') or not x.strip() for x in lines]
            self.send_frontend_msg(
                'cell-kernel', [self._meta['cell_id'], 'SoS'])
            if all(empties):
                return {'status': 'ok', 'payload': [], 'user_expressions': {}, 'execution_count': self._execution_count}
            else:
                idx = empties.index(False)
                if idx != 0:
                    # not start from empty, but might have magic etc
                    return self._do_execute('\n'.join(lines[idx:]) + '\n', silent, store_history, user_expressions, allow_stdin)

            # if there is no more empty, magic etc, enter workflow mode
            # run sos
            try:
                self.run_sos_code(code, silent)
                if self._meta['cell_id']:
                    self._meta['cell_id'] = ""
                return {'status': 'ok', 'payload': [], 'user_expressions': {}, 'execution_count': self._execution_count}
            except Exception as e:
                self.warn(str(e))
                return {'status': 'error',
                        'ename': e.__class__.__name__,
                        'evalue': str(e),
                        'traceback': [],
                        'execution_count': self._execution_count,
                        }
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


if __name__ == '__main__':
    from ipykernel.kernelapp import IPKernelApp

    IPKernelApp.launch_instance(kernel_class=SoS_Kernel)
