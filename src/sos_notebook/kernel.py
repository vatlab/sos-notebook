#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import contextlib
import fnmatch
import logging
import os
import subprocess
import sys
import time
from collections import defaultdict
from textwrap import dedent

import pandas as pd
import pkg_resources
from ipykernel.ipkernel import IPythonKernel
from IPython.core.display import HTML

from IPython.utils.tokenutil import line_at_cursor, token_at_cursor
from jupyter_client import manager
from sos._version import __sos_version__, __version__
from sos.eval import SoS_eval, SoS_exec
from sos.syntax import SOS_SECTION_HEADER, SOS_DIRECTIVE
from sos.utils import WorkflowDict, env, short_repr, load_config_files
from sos.targets import file_target
from sos.executor_utils import prepare_env

from ._version import __version__ as __notebook_version__
from .completer import SoS_Completer
from .inspector import SoS_Inspector
from .workflow_executor import (run_sos_workflow, execute_scratch_cell,
                                NotebookLoggingHandler, start_controller)
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
            self.kernel.send_response(
                self.kernel.iopub_socket, 'display_data', {
                    'metadata': {},
                    'data': {
                        'text/html':
                            HTML(f'<div class="sos_hint">{hint_line}</div>'
                                ).data
                    }
                })
        if content:
            if self.kernel._meta['capture_result'] is not None:
                self.kernel._meta['capture_result'].append(('stream', {
                    'name': self.name,
                    'text': content
                }))
            if self.kernel._meta['render_result'] is False:
                self.kernel.send_response(self.kernel.iopub_socket, 'stream', {
                    'name': self.name,
                    'text': content
                })

    def flush(self):
        pass


__all__ = ['SoS_Kernel']


class subkernel(object):
    # a class to information on subkernel
    def __init__(self,
                 name=None,
                 kernel=None,
                 language='',
                 color='',
                 options={},
                 codemirror_mode=''):
        self.name = name
        self.kernel = kernel
        self.language = language
        self.color = color
        self.options = options
        self.codemirror_mode = codemirror_mode

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
            f"failed to translate message {msg_type} to transient_display_data message"
        )


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
            for lname, knames in kernel.supported_languages[
                    x].supported_kernels.items():
                for kname in knames:
                    if x != kname:
                        lan_map[kname] = (lname,
                                          self.get_background_color(
                                              self.language_info[x], lname),
                                          getattr(self.language_info[x],
                                                  'options', {}), '')
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
                    subkernel(
                        name='SoS',
                        kernel='sos',
                        options={
                            'variable_pattern':
                                r'^\s*[_A-Za-z0-9\.]+\s*$',
                            'assignment_pattern':
                                r'^\s*([_A-Za-z0-9\.]+)\s*=.*$'
                        },
                        codemirror_mode='sos'))
            elif spec in lan_map:
                # e.g. ir ==> R
                self._kernel_list.append(
                    subkernel(
                        name=lan_map[spec][0],
                        kernel=spec,
                        language=lan_map[spec][0],
                        color=lan_map[spec][1],
                        options=lan_map[spec][2]))
            elif any(fnmatch.fnmatch(spec, x) for x in lan_map.keys()):
                matched = [
                    y for x, y in lan_map.items() if fnmatch.fnmatch(spec, x)
                ][0]
                self._kernel_list.append(
                    subkernel(
                        name=matched[0],
                        kernel=spec,
                        language=matched[0],
                        color=matched[1],
                        options=matched[2]))
            else:
                # undefined language also use default theme color
                self._kernel_list.append(
                    subkernel(
                        name=spec,
                        kernel=spec,
                        language=km.get_kernel_spec(spec).language))

    def kernel_list(self):
        return self._kernel_list

    default_cm_mode = {
        'sos': '',
        'python': {
            'name': 'python',
            'version': 3
        },
        'python2': {
            'name': 'python',
            'version': 2
        },
        'python3': {
            'name': 'python',
            'version': 3
        },
        'r': 'r',
        'report': 'markdown',
        'pandoc': 'markdown',
        'download': 'markdown',
        'markdown': 'markdown',
        'ruby': 'ruby',
        'sas': 'sas',
        'bash': 'shell',
        'sh': 'shell',
        'julia': 'julia',
        'run': 'shell',
        'javascript': 'javascript',
        'typescript': {
            'name': "javascript",
            'typescript': True
        },
        'octave': 'octave',
        'matlab': 'octave',
    }

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
            return plugin.background_color.get(
                lan, next(iter(plugin.background_color.values())))

    def find(self,
             name,
             kernel=None,
             language=None,
             color=None,
             codemirror_mode='',
             notify_frontend=True):
        codemirror_mode = codemirror_mode if codemirror_mode else self.default_cm_mode.get(
            'codemirror_mode', codemirror_mode)

        # find from subkernel name
        def update_existing(idx):
            x = self._kernel_list[idx]

            #  [Bash, some_sh, ....]
            # but the provided kernel does not match...
            if (kernel is not None and kernel != x.kernel):
                env.logger.warning(
                    f"Notebook uses kernel {x.kernel} for language {x.language}, but local system uses kernel {kernel} instead."
                )
                self._kernel_list[idx].kernel = kernel
                if notify_frontend:
                    self.notify_frontend()
            #  similarly, identified by kernel but language names are different
            if language not in (None, '', 'None') and language != x.language:
                env.logger.warning(
                    f"Notebook uses language {x.language} for kernel {x.kernel}, but local system uses language {language} instead."
                )
                self._kernel_list[idx].language = language
                if notify_frontend:
                    self.notify_frontend()
            if codemirror_mode:
                self._kernel_list[idx].codemirror_mode = codemirror_mode
            if color is not None:
                if color == 'default':
                    if self._kernel_list[idx].language:
                        self._kernel_list[idx].color = self.get_background_color(
                            self.language_info[self._kernel_list[idx].language],
                            self._kernel_list[idx].language)
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
                    f'Unrecognized Jupyter kernel name {kernel}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                )
            # now this a new instance for an existing kernel
            kdef = [x for x in self._kernel_list if x.kernel == kernel][0]
            if not language:
                if color == 'default':
                    if kdef.language:
                        color = self.get_background_color(
                            self.language_info[kdef.language], kdef.language)
                    else:
                        color = kdef.color
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        kdef.kernel,
                        kdef.language,
                        kdef.color if color is None else color,
                        getattr(self.language_info[kdef.language], 'options',
                                {}) if kdef.language else {},
                        codemirror_mode=codemirror_mode))
                if notify_frontend:
                    self.notify_frontend()
                return new_def
            else:
                # if language is defined,
                if ':' in language:
                    # if this is a new module, let us create an entry point and load
                    from pkg_resources import EntryPoint
                    mn, attr = language.split(':', 1)
                    ep = EntryPoint(
                        name=kernel,
                        module_name=mn,
                        attrs=tuple(attr.split('.')))
                    try:
                        plugin = ep.resolve()
                        self.language_info[name] = plugin
                        # for convenience, we create two entries for, e.g. R and ir
                        # but only if there is no existing definition
                        for supported_lan, supported_kernels in plugin.supported_kernels.items(
                        ):
                            for supported_kernel in supported_kernels:
                                if name != supported_kernel and supported_kernel not in self.language_info:
                                    self.language_info[
                                        supported_kernel] = plugin
                            if supported_lan not in self.language_info:
                                self.language_info[supported_lan] = plugin
                    except Exception as e:
                        raise RuntimeError(
                            f'Failed to load language {language}: {e}')
                    #
                    if color == 'default':
                        color = self.get_background_color(plugin, kernel)
                    new_def = self.add_or_replace(
                        subkernel(
                            name,
                            kdef.kernel,
                            kernel,
                            kdef.color if color is None else color,
                            getattr(plugin, 'options', {}),
                            codemirror_mode=codemirror_mode))
                else:
                    # if should be defined ...
                    if language not in self.language_info:
                        raise RuntimeError(
                            f'Unrecognized language definition {language}, which should be a known language name or a class in the format of package.module:class'
                        )
                    #
                    self.language_info[name] = self.language_info[language]
                    if color == 'default':
                        color = self.get_background_color(
                            self.language_info[name], language)
                    new_def = self.add_or_replace(
                        subkernel(
                            name,
                            kdef.kernel,
                            language,
                            kdef.color if color is None else color,
                            getattr(self.language_info[name], 'options', {}),
                            codemirror_mode=codemirror_mode))
                if notify_frontend:
                    self.notify_frontend()
                return new_def
        elif language is not None:
            # kernel is not defined and we only have language
            if ':' in language:
                # if this is a new module, let us create an entry point and load
                from pkg_resources import EntryPoint
                mn, attr = language.split(':', 1)
                ep = EntryPoint(
                    name='__unknown__',
                    module_name=mn,
                    attrs=tuple(attr.split('.')))
                try:
                    plugin = ep.resolve()
                    self.language_info[name] = plugin
                except Exception as e:
                    raise RuntimeError(
                        f'Failed to load language {language}: {e}')

                avail_kernels = [
                    y.kernel
                    for y in self._kernel_list
                    if y.kernel in sum(plugin.supported_kernels.values(), []) or
                    any(
                        fnmatch.fnmatch(y.kernel, x)
                        for x in sum(plugin.supported_kernels.values(), []))
                ]

                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                        .format(
                            ', '.join(
                                sum(plugin.supported_kernels.values(), [])),
                            language))
                # use the first available kernel
                # find the language that has the kernel
                lan_name = list({
                    x: y
                    for x, y in plugin.supported_kernels.items()
                    if avail_kernels[0] in y or any(
                        fnmatch.fnmatch(avail_kernels[0], z) for z in y)
                }.keys())[0]
                if color == 'default':
                    color = self.get_background_color(plugin, lan_name)
                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        avail_kernels[0],
                        lan_name,
                        self.get_background_color(plugin, lan_name)
                        if color is None else color,
                        getattr(plugin, 'options', {}),
                        codemirror_mode=codemirror_mode))
            else:
                # if a language name is specified (not a path to module), if should be defined in setup.py
                if language not in self.language_info:
                    raise RuntimeError(
                        f'Unrecognized language definition {language}')
                #
                plugin = self.language_info[language]
                if language in plugin.supported_kernels:
                    avail_kernels = [
                        y.kernel for y in self._kernel_list if
                        y.kernel in plugin.supported_kernels[language] or any(
                            fnmatch.fnmatch(y.kernel, x)
                            for x in plugin.supported_kernels[language])
                    ]
                else:
                    avail_kernels = [
                        y.kernel for y in self._kernel_list if y.kernel in
                        sum(plugin.supported_kernels.values(), []) or any(
                            fnmatch.fnmatch(y.kernel, x)
                            for x in sum(plugin.supported_kernels.values(), []))
                    ]
                if not avail_kernels:
                    raise ValueError(
                        'Failed to find any of the kernels {} supported by language {}. Please make sure it is properly installed and appear in the output of command "jupyter kenelspec list"'
                        .format(
                            ', '.join(
                                sum(
                                    self.language_info[language]
                                    .supported_kernels.values(), [])),
                            language))

                new_def = self.add_or_replace(
                    subkernel(
                        name,
                        avail_kernels[0],
                        language,
                        self.get_background_color(self.language_info[language],
                                                  language)
                        if color is None or color == 'default' else color,
                        getattr(self.language_info[language], 'options', {}),
                        codemirror_mode=codemirror_mode))

            self.notify_frontend()
            return new_def
        else:
            # let us check if there is something wrong with the pre-defined language
            for entrypoint in pkg_resources.iter_entry_points(
                    group='sos_languages'):
                if entrypoint.name == name:
                    # there must be something wrong, let us trigger the exception here
                    entrypoint.load()
            # if nothing is triggerred, kernel is not defined, return a general message
            raise ValueError(
                f'No subkernel named {name} is found. Please make sure that you have the kernel installed (listed in the output of "jupyter kernelspec list" and usable in jupyter by itself), install appropriate language module (e.g. "pip install sos-r"), restart jupyter notebook and try again.'
            )

    def update(self, notebook_kernel_list):
        for kinfo in notebook_kernel_list:
            try:
                # if we can find the kernel, fine...
                self.find(
                    name=kinfo[0],
                    kernel=kinfo[1],
                    language=kinfo[2],
                    color=kinfo[3],
                    codemirror_mode='' if len(kinfo) >= 4 else kinfo[4],
                    notify_frontend=False)
            except Exception as e:
                # otherwise do not worry about it.
                env.logger.warning(
                    f'Failed to locate subkernel {kinfo[0]} with kernerl "{kinfo[1]}" and language "{kinfo[2]}": {e}'
                )

    def notify_frontend(self):
        self._kernel_list.sort(key=lambda x: x.name)
        self.sos_kernel.send_frontend_msg('kernel-list', [[
            x.name, x.kernel, x.language, x.color, x.codemirror_mode, x.options
        ] for x in self._kernel_list])


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
                env.log_to_file(
                    'KERNEL', f'Failed to load registered language {name}: {e}')
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
        env.log_to_file(
            'KERNEL',
            f'Starting SoS Kernel version {__notebook_version__} with SoS {__version__}'
        )

        self.kernels = {}
        # self.shell = InteractiveShell.instance()
        self.format_obj = self.shell.display_formatter.format

        self._meta = {
            'workflow': '',
            'workflow_mode': False,
            'render_result': False,
            'capture_result': None,
            'cell_id': 0,
            'notebook_name': '',
            'notebook_path': '',
            'use_panel': True,
            'use_iopub': False,
            'default_kernel': 'SoS',
            'cell_kernel': 'SoS',
            'toc': '',
            'batch_mode': False
        }
        self._debug_mode = False
        self._supported_languages = None
        self._completer = None
        self._inspector = None
        self._real_execution_count = 1
        self._execution_count = 1
        self.frontend_comm = None
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
            'SOS_VERSION', 'CONFIG', 'step_name', '__builtins__', 'input',
            'output', 'depends'
        }
        env.logger.handlers = [
            x for x in env.logger.handlers
            if type(x) is not logging.StreamHandler
        ]
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
                elif k == 'cancel-workflow':
                    from .workflow_executor import cancel_workflow
                    cancel_workflow(v[0], self)
                elif k == 'execute-workflow':
                    from .workflow_executor import execute_pending_workflow
                    execute_pending_workflow(v, self)
                elif k == 'update-task-status':
                    if not isinstance(v, list):
                        continue
                    # split by host ...
                    host_status = defaultdict(list)
                    for name in v:
                        try:
                            tqu, tid = name.rsplit('_', 1)
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
                            self.send_frontend_msg(
                                'task_status', {
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
                        self.send_frontend_msg(
                            'alert', f'Failed to paste clipboard as table: {e}')
                elif k == 'notebook-version':
                    # send the version of notebook, right now we will not do anything to it, but
                    # we will send the version of sos-notebook there
                    self.send_frontend_msg('notebook-version',
                                           __notebook_version__)
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
            elif self._meta['use_iopub']:
                self.send_response(self.iopub_socket, 'transient_display_data',
                                   make_transient_msg(msg_type, msg))
            else:
                self.frontend_comm.send(
                    make_transient_msg(msg_type, msg),
                    {'msg_type': 'transient_display_data'})
        elif self.frontend_comm:
            self.frontend_comm.send({} if msg is None else msg,
                                    {'msg_type': msg_type})
        else:
            self.warn(
                'Frontend communicator is broken. Please restart jupyter server'
            )

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
            default_items = [
                x for x in env.sos_dict.keys()
                if x.startswith('sos') and x not in self.original_keys
            ]
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
                    'Magic %get without option --kernel can only be executed by subkernels'
                )
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
                self.put_vars_to(items, to_kernel=my_kernel, explicit=explicit)
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
                    'Magic %put without option --kernel can only be executed by subkernels'
                )
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
                        items,
                        to_kernel=self.subkernels.find(to_kernel).language)
                else:
                    objects = lan(self, kinfo.kernel).put_vars(
                        items, to_kernel='SoS')
            except Exception as e:
                # if somethign goes wrong in the subkernel does not matter
                env.log_to_file(
                    'MAGIC',
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
                            f'Failed to put variables {items} to SoS kernel: {e}'
                        )
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
                    f'Unrecognized return value of type {object.__class__.__name__} for action %put'
                )
                return

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
                        lines[idx] = lines[idx][:-1] + lines[idx+1]
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
                from IPython.core.inputtransformer2 import TransformerManager as ipf
            except ImportError:
                from IPython.core.inputsplitter import InputSplitter as ipf
            code = '\n'.join(lines) + '\n\n'
            res = ipf().check_complete(code)
            env.log_to_file(f'MESSAGE', f'SoS kernel returns {res} for code {code}')
            return {'status': res[0], 'indent': res[1]}
        # non-SoS kernels
        try:
            cell_kernel = self.subkernels.find(self.editor_kernel)
            if cell_kernel.name not in self.kernels:
                try:
                    orig_kernel = self.kernel
                    # switch to start the new kernel
                    self.switch_kernel(cell_kernel.name)
                finally:
                    self.switch_kernel(orig_kernel)

            KC = self.kernels[cell_kernel.name][1]
            # clear the shell channel
            while KC.shell_channel.msg_ready():
                KC.shell_channel.get_msg()
            code = '\n'.join(lines)
            KC.is_complete(code)
            msg = KC.shell_channel.get_msg()
            if msg['header']['msg_type'] == 'is_complete_reply':
                env.log_to_file(f'MESSAGE', f'{self.kernel} kernel returns {msg["content"]} for code {code}')
                return msg['content']

            raise RuntimError(
                f"is_complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead"
            )
        except Exception as e:
            env.logger.debug(f'Completion fail with exception: {e}')
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
                env.log_to_file('KERNEL',
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
                        env.log_to_file(
                            'MESSAGE',
                            f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead"
                        )
                        break
            except Exception as e:
                env.log_to_file('KERNEL',
                                f'Completion fail with exception: {e}')

    def do_complete(self, code, cursor_pos):
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
                try:
                    orig_kernel = self.kernel
                    # switch to start the new kernel
                    self.switch_kernel(cell_kernel.name)
                finally:
                    self.switch_kernel(orig_kernel)

            KC = self.kernels[cell_kernel.name][1]
            # clear the shell channel
            while KC.shell_channel.msg_ready():
                KC.shell_channel.get_msg()
            KC.complete(code, cursor_pos)
            msg = KC.shell_channel.get_msg()
            if msg['header']['msg_type'] == 'complete_reply':
                return msg['content']

            raise RuntimError(
                f"complete_reply not obtained: {msg['header']['msg_type']} {msg['content']} returned instead"
            )
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
            self.send_response(self.iopub_socket, 'stream', {
                'name': 'stderr',
                'text': message
            })

    def run_cell(self, code, silent, store_history, on_error=None):
        #
        if not self.KM.is_alive():
            self.send_response(
                self.iopub_socket, 'stream',
                dict(
                    name='stdout',
                    text='Restarting kernel "{}"\n'.format(self.kernel)))
            self.KM.restart_kernel(now=False)
            self.KC = self.KM.client()
        # flush stale replies, which could have been ignored, due to missed heartbeats
        while self.KC.shell_channel.msg_ready():
            self.KC.shell_channel.get_msg()
        # executing code in another kernel
        self.KC.execute(code, silent=silent, store_history=store_history)

        # first thing is wait for any side effects (output, stdin, etc.)
        iopub_started = False
        iopub_ended = False
        shell_ended = False
        res = None
        while not (iopub_started and iopub_ended and shell_ended):
            # display intermediate print statements, etc.
            while self.KC.stdin_channel.msg_ready():
                sub_msg = self.KC.stdin_channel.get_msg()
                env.log_to_file(
                    'MESSAGE',
                    f"MSG TYPE {sub_msg['header']['msg_type']} CONTENT  {sub_msg}"
                )
                if sub_msg['header']['msg_type'] != 'input_request':
                    self.send_response(self.stdin_socket,
                                       sub_msg['header']['msg_type'],
                                       sub_msg["content"])
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
                    f"IOPUB MSG TYPE {sub_msg['header']['msg_type']} CONTENT  {sub_msg['content']}"
                )
                if msg_type == 'status':
                    if sub_msg["content"]["execution_state"] == 'busy':
                        iopub_started = True
                    elif iopub_started and sub_msg["content"][
                            "execution_state"] == 'idle':
                        iopub_ended = True
                    continue
                if msg_type in ('execute_input', 'execute_result'):
                    # override execution count with the master count,
                    # not sure if it is needed
                    sub_msg['content'][
                        'execution_count'] = self._execution_count
                #
                if msg_type in [
                        'display_data', 'stream', 'execute_result',
                        'update_display_data'
                ]:
                    if self._meta['capture_result'] is not None:
                        self._meta['capture_result'].append(
                            (msg_type, sub_msg['content']))
                    if msg_type == 'execute_result' or (
                            not silent and
                            self._meta['render_result'] is False):
                        self.send_response(self.iopub_socket, msg_type,
                                           sub_msg['content'])
                else:
                    self.send_response(self.iopub_socket, msg_type,
                                       sub_msg['content'])
            if self.KC.shell_channel.msg_ready():
                # now get the real result
                reply = self.KC.get_shell_msg()
                reply['content']['execution_count'] = self._execution_count
                env.log_to_file('MESSAGE', f'GET SHELL MSG {reply}')
                res = reply['content']
                shell_ended = True
            time.sleep(0.001)
        return res

    def switch_kernel(self,
                      kernel,
                      in_vars=None,
                      kernel_name=None,
                      language=None,
                      color=None):
        # switching to a non-sos kernel
        if not kernel:
            kinfo = self.subkernels.find(self.kernel)
            self.send_response(
                self.iopub_socket, 'stream',
                dict(
                    name='stdout',
                    text='''\
Active subkernels: {}
Available subkernels:\n{}'''.format(
                        ', '.join(self.kernels.keys()), '\n'.join([
                            '    {} ({})'.format(x.name, x.kernel)
                            for x in self.subkernels.kernel_list()
                        ]))))
            return
        kinfo = self.subkernels.find(kernel, kernel_name, language, color)
        if kinfo.name == self.kernel:
            return
        elif kinfo.name == 'SoS':
            # non-SoS to SoS
            self.put_vars_to(in_vars)
            self.kernel = 'SoS'
        elif self.kernel != 'SoS':
            # Non-SoS to Non-SoS
            self.switch_kernel('SoS', in_vars)
            self.switch_kernel(kinfo.name, in_vars)
        else:
            # SoS to non-SoS
            env.log_to_file('KERNEL',
                            f'Switch from {self.kernel} to {kinfo.name}')
            # case when self.kernel == 'sos', kernel != 'sos'
            # to a subkernel
            new_kernel = False
            if kinfo.name not in self.kernels:
                # start a new kernel
                try:
                    env.log_to_file('KERNEL',
                                    f'Starting subkernel {kinfo.name}')
                    self.kernels[kinfo.name] = manager.start_new_kernel(
                        startup_timeout=60,
                        kernel_name=kinfo.kernel,
                        cwd=os.getcwd())
                    new_kernel = True
                except Exception as e:
                    # try toget error message
                    import tempfile
                    with tempfile.TemporaryFile() as ferr:
                        try:
                            # this should fail
                            manager.start_new_kernel(
                                startup_timeout=60,
                                kernel_name=kinfo.kernel,
                                cwd=os.getcwd(),
                                stdout=subprocess.DEVNULL,
                                stderr=ferr)
                        except:
                            ferr.seek(0)
                            self.warn(
                                f'Failed to start kernel "{kernel}". {e}\nError Message:\n{ferr.read().decode()}'
                            )
                    return
            self.KM, self.KC = self.kernels[kinfo.name]
            self.kernel = kinfo.name
            if new_kernel and not kinfo.codemirror_mode:
                self.KC.kernel_info()
                kinfo.codemirror_mode = self.KC.get_shell_msg(
                    timeout=10)['content']['language_info'].get(
                        'codemirror_mode', '')
                self.subkernels.notify_frontend()
            if new_kernel and self.kernel in self.supported_languages:
                lan_module = self.supported_languages[self.kernel](self,
                                                                   kinfo.kernel)
                init_stmts = lan_module.init_statements

                if hasattr(lan_module, '__version__'):
                    module_version = f' (version {lan_module.__version__})'
                else:
                    module_version = f' (version unavailable)'

                env.log_to_file(
                    'KERNEL',
                    f'Loading language module for kernel {kinfo.name}{module_version}'
                )
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
                self.send_response(
                    self.iopub_socket, 'stream',
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
            self.send_response(
                self.iopub_socket, 'stream',
                dict(
                    name='stdout',
                    text='Specify one of the kernels to shutdown: SoS{}\n'
                    .format(''.join(f', {x}' for x in self.kernels))))
        #stop_controller(self.controller)

    def get_response(self, statement, msg_types, name=None):
        # get response of statement of specific msg types.
        while self.KC.shell_channel.msg_ready():
            self.KC.shell_channel.get_msg()
        while self.KC.iopub_channel.msg_ready():
            sub_msg = self.KC.iopub_channel.get_msg()
            if sub_msg['header']['msg_type'] != 'status':
                env.log_to_file(
                    'MESSAGE',
                    f"Overflow message in iopub {sub_msg['header']['msg_type']} {sub_msg['content']}"
                )
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
                env.log_to_file('MESSAGE',
                                f'Received {msg_type} {sub_msg["content"]}')
                if msg_type == 'status':
                    if sub_msg["content"]["execution_state"] == 'busy':
                        iopub_started = True
                    elif iopub_started and sub_msg["content"][
                            "execution_state"] == 'idle':
                        iopub_ended = True
                    continue
                if msg_type in msg_types and (name is None or
                                              sub_msg['content'].get(
                                                  'name', None) in name):
                    env.log_to_file(
                        'MESSAGE',
                        f'Capture response: {msg_type}: {sub_msg["content"]}')
                    responses.append([msg_type, sub_msg['content']])
                else:
                    env.log_to_file(
                        'MESSAGE',
                        f'Non-response: {msg_type}: {sub_msg["content"]}')
                    #
                    # we ignore the messages we are not interested.
                    #
                    #self.send_response(
                    #    self.iopub_socket, msg_type, sub_msg['content'])
            if self.KC.shell_channel.msg_ready():
                # now get the real result
                reply = self.KC.get_shell_msg()
                env.log_to_file('MESSAGE', f'GET SHELL MSG {reply}')
                shell_ended = True
            time.sleep(0.001)

        if not responses:
            env.log_to_file(
                'MESSAGE',
                f'Failed to get a response from message type {msg_types} for the execution of {statement}'
            )
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
                        run_in_queue=self._workflow_mode == 'nowait')
                else:
                    res = execute_scratch_cell(
                        code=code, raw_args=self.options, kernel=self)
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
                return {
                    'status': 'abort',
                    'execution_count': self._execution_count
                }
            finally:
                sys.stderr.flush()
                sys.stdout.flush()
        #
        if False:
            input_files = [
                str(x)
                for x in env.sos_dict.get('step_input', [])
                if isinstance(x, file_target)
            ]
            output_files = [
                str(x)
                for x in env.sos_dict.get('step_output', [])
                if isinstance(x, file_target)
            ]

            # use a table to list input and/or output file if exist
            if output_files and not (hasattr(self, '_no_auto_preview') and
                                     self._no_auto_preview):
                title = f'%preview {" ".join(output_files)}'
                if not self._meta['use_panel']:
                    self.send_response(
                        self.iopub_socket, 'display_data', {
                            'metadata': {},
                            'data': {
                                'text/html':
                                    HTML(f'<div class="sos_hint">{title}</div>'
                                        ).data
                            }
                        })

                if hasattr(self, 'in_sandbox') and self.in_sandbox:
                    # if in sand box, do not link output to their files because these
                    # files will be removed soon.
                    self.send_frontend_msg(
                        'display_data', {
                            'metadata': {},
                            'data': {
                                'text/html':
                                    '''<div class="sos_hint"> input: {}<br>output: {}\n</div>'''
                                    .format(', '.join(x for x in input_files),
                                            ', '.join(x for x in output_files))
                            }
                        })
                else:
                    self.send_frontend_msg(
                        'display_data', {
                            'metadata': {},
                            'data': {
                                'text/html':
                                    '''<div class="sos_hint"> input: {}<br>output: {}\n</div>'''
                                    .format(
                                        ', '.join(
                                            f'<a target="_blank" href="{x}">{x}</a>'
                                            for x in input_files),
                                        ', '.join(
                                            f'<a target="_blank" href="{x}">{x}</a>'
                                            for x in output_files))
                            }
                        })

                Preview_Magic(self).handle_magic_preview(output_files, "SoS")

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
            if self._meta['capture_result'] is not None:
                self._meta['capture_result'].append(
                    ('execute_result', format_dict))
            env.log_to_file('MESSAGE',
                            f'IOPUB execute_result with content {format_dict}')
            self.send_response(
                self.iopub_socket, 'execute_result', {
                    'execution_count': self._execution_count,
                    'data': format_dict,
                    'metadata': md_dict
                })

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
                'use_iopub': False,
                'default_kernel': self.kernel,
                'cell_kernel': self.kernel,
                'toc': '',
                'batch_mode': False
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
                meta['cell_id'] if 'cell_id' in meta else "",
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
            'toc':
                meta.get('toc', ''),
            'batch_mode':
                meta.get('batch_mode', False)
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

    def do_execute(self,
                   code,
                   silent,
                   store_history=True,
                   user_expressions=None,
                   allow_stdin=True):
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
            if self.subkernels.find(
                    self._meta['default_kernel']).name != self.subkernels.find(
                        self.kernel).name:
                self.switch_kernel(self._meta['default_kernel'])
                # evaluate user expression
        except Exception as e:
            self.warn(
                f'Failed to switch to language {self._meta["default_kernel"]}: {e}\n'
            )
            return {
                'status': 'error',
                'ename': e.__class__.__name__,
                'evalue': str(e),
                'traceback': [],
                'execution_count': self._execution_count,
            }
        # switch to cell kernel
        try:
            if self.subkernels.find(
                    self._meta['cell_kernel']).name != self.subkernels.find(
                        self.kernel).name:
                self.switch_kernel(self._meta['cell_kernel'])
        except Exception as e:
            self.warn(
                f'Failed to switch to language {self._meta["cell_kernel"]}: {e}\n'
            )
            return {
                'status': 'error',
                'ename': e.__class__.__name__,
                'evalue': str(e),
                'traceback': [],
                'execution_count': self._execution_count,
            }
        # execute with cell kernel
        try:
            ret = self._do_execute(
                code=code,
                silent=silent,
                store_history=store_history,
                user_expressions=user_expressions,
                allow_stdin=allow_stdin)
        except Exception as e:
            self.warn(e)
            return {
                'status': 'error',
                'ename': e.__class__.__name__,
                'evalue': str(e),
                'traceback': [],
                'execution_count': self._execution_count,
            }

        if ret is None:
            ret = {
                'status': 'ok',
                'payload': [],
                'user_expressions': {},
                'execution_count': self._execution_count
            }

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

    def _do_execute(self,
                    code,
                    silent,
                    store_history=True,
                    user_expressions=None,
                    allow_stdin=True):
        # handles windows/unix newline
        code = '\n'.join(code.splitlines()) + '\n'
        if code == 'import os\n_pid = os.getpid()':
            # this is a special probing command from vim-ipython. Let us handle it specially
            # so that vim-python can get the pid.
            return
        for magic in self.magics.values():
            if magic.match(code):
                return magic.apply(code, silent, store_history,
                                   user_expressions, allow_stdin)
        if self.kernel != 'SoS':
            # handle string interpolation before sending to the underlying kernel
            if self._meta['cell_id']:
                self.send_frontend_msg('cell-kernel',
                                       [self._meta['cell_id'], self.kernel])
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
                return {
                    'status': 'abort',
                    'execution_count': self._execution_count
                }
        else:
            # if the cell starts with comment, and newline, remove it
            lines = code.splitlines()
            empties = [x.startswith('#') or not x.strip() for x in lines]
            self.send_frontend_msg('cell-kernel',
                                   [self._meta['cell_id'], 'SoS'])
            if all(empties):
                return {
                    'status': 'ok',
                    'payload': [],
                    'user_expressions': {},
                    'execution_count': self._execution_count
                }
            else:
                idx = empties.index(False)
                if idx != 0 and (lines[idx].startswith('%') or
                                 lines[idx].startswith('!')):
                    # not start from empty, but might have magic etc
                    return self._do_execute('\n'.join(lines[idx:]) + '\n',
                                            silent, store_history,
                                            user_expressions, allow_stdin)

            # if there is no more empty, magic etc, enter workflow mode
            # run sos
            try:
                self.run_sos_code(code, silent)
                return {
                    'status': 'ok',
                    'payload': [],
                    'user_expressions': {},
                    'execution_count': self._execution_count
                }
            except Exception as e:
                self.warn(str(e))
                return {
                    'status': 'error',
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
