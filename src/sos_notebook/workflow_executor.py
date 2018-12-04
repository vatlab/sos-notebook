#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.
import datetime
import logging
import multiprocessing as mp
import os
import re
import shlex
import sys
import time
from collections import defaultdict
from threading import Event
from typing import DefaultDict, Union

import psutil
import zmq
from IPython.core.display import HTML
from sos.__main__ import get_run_parser
from sos.controller import (Controller, connect_controllers,
                            disconnect_controllers)
from sos.eval import SoS_exec
from sos.executor_utils import prepare_env
from sos.parser import SoS_Script
from sos.section_analyzer import analyze_section
from sos.syntax import SOS_SECTION_HEADER
from sos.targets import (RemovedTarget, UnavailableLock, UnknownTarget,
                         sos_targets)
from sos.utils import _parse_error, env, get_traceback, pexpect_run
from sos.workflow_executor import Base_Executor

from .step_executor import Interactive_Step_Executor


class NotebookLoggingHandler(logging.Handler):
    def __init__(self, level, kernel=None, title="Log Messages"):
        super(NotebookLoggingHandler, self).__init__(level)
        self.kernel = kernel
        self.title = title

    def setTitle(self, title):
        self.title = title

    def emit(self, record):
        msg = re.sub(r'``([^`]*)``',
                     r'<span class="sos_highlight">\1</span>', record.msg)
        self.kernel.send_frontend_msg('display_data', {
            'metadata': {},
            'data': {'text/html': f'<div class="sos_logging sos_{record.levelname.lower()}">{record.levelname}: {msg}</div>'}
        }, title=self.title, append=True, page='SoS')
        #self.kernel.send_response(self.kernel.iopub_socket, 'stream',
        #                          {'name': 'stdout', 'text': record.msg})


def start_controller(kernel):
    env.zmq_context = zmq.Context()
    # ready to monitor other workflows
    env.config['exec_mode'] = 'master'

    ready = Event()
    controller = Controller(ready, kernel)
    controller.start()
    # wait for the thread to start with a signature_req saved to env.config
    ready.wait()
    connect_controllers(env.zmq_context)
    return controller


def stop_controller(controller):
    if not controller:
        return
    env.controller_req_socket.send_pyobj(['done'])
    env.controller_req_socket.recv()
    disconnect_controllers()
    controller.join()


def execute_scratch_cell(code, raw_args, kernel):
    # we then have to change the parse to disable args.workflow when
    # there is no workflow option.
    raw_args = shlex.split(raw_args) if isinstance(raw_args, str) else raw_args
    if code is None or '-h' in raw_args:
        parser = get_run_parser(interactive=True, with_workflow=True)
        parser.print_help()
        return
    if raw_args and raw_args[0].lstrip().startswith('-'):
        parser = get_run_parser(interactive=True, with_workflow=False)
        parser.error = _parse_error
        args, workflow_args = parser.parse_known_args(raw_args)
        args.workflow = None
    else:
        parser = get_run_parser(interactive=True, with_workflow=True)
        parser.error = _parse_error
        args, workflow_args = parser.parse_known_args(raw_args)

    if not code.strip():
        return

    # for reporting purpose
    sys.argv = ['%run'] + raw_args
    env.verbosity = args.verbosity

    if not isinstance(env.logger.handlers[0], NotebookLoggingHandler):
        env.logger.handlers = []
        levels = {
            0: logging.ERROR,
            1: logging.WARNING,
            2: logging.INFO,
            3: logging.DEBUG,
            4: logging.TRACE,
            None: logging.INFO
        }
        env.logger.addHandler(NotebookLoggingHandler(
            levels[env.verbosity], kernel, title=' '.join(sys.argv)))
    else:
        env.logger.handers[0].setTitle(' '.join(sys.argv))

    # clear __step_input__, __step_output__ etc because there is
    # no concept of passing input/outputs across cells.
    env.sos_dict.set('__step_output__', sos_targets([]))
    for k in ['__step_input__', '__default_output__', 'step_input', 'step_output',
              'step_depends', '_input', '_output', '_depends']:
        env.sos_dict.pop(k, None)

    config = {
        'config_file': args.__config__,
        'default_queue': '' if args.__queue__ is None else args.__queue__,
        'run_mode': 'dryrun' if args.dryrun else 'interactive',
        'verbosity': args.verbosity,
        # wait if -w or in dryrun mode, not wait if -W, otherwise use queue default
        'max_procs': args.__max_procs__,
        'max_running_jobs': args.__max_running_jobs__,
        # for infomration and resume only
        'workdir': os.getcwd(),
        'workflow': args.workflow,
        'targets': args.__targets__,
        'workflow_args': workflow_args,
        'workflow_id': '0',

        # interactive work is also a slave of the controller
        'slave_id': kernel.cell_id,
    }

    env.sos_dict.set('workflow_id', '0')
    env.config.update(config)
    prepare_env('')

    try:
        if not any([SOS_SECTION_HEADER.match(line) or line.startswith('%from') or line.startswith('%include') for line in code.splitlines()]):
            code = '[scratch_0]\n' + code
            script = SoS_Script(content=code)
        else:
            return
        workflow = script.workflow(args.workflow)
        section = workflow.sections[0]
        res = analyze_section(section)
        env.sos_dict.quick_update({
            '__signature_vars__': res['signature_vars'],
            '__environ_vars__': res['environ_vars'],
            '__changed_vars__': res['changed_vars']
        })
        executor = Interactive_Step_Executor(section, mode='interactive')
        return executor.run()['__last_res__']
    except (UnknownTarget, RemovedTarget) as e:
        raise RuntimeError(f'Unavailable target {e.target}')
    except SystemExit:
        # this happens because the executor is in resume mode but nothing
        # needs to be resumed, we simply pass
        return
    except Exception:
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        raise


class Tapped_Executor(mp.Process):
    def __init__(self, code, args, config):
        # the worker process knows configuration file, command line argument etc
        super(Tapped_Executor, self).__init__()
        self.code = code
        self.args = args
        self.config = config

    def run(self):
        env.config.update(self.config)
        # start a socket?
        context = zmq.Context()
        stdout_socket = context.socket(zmq.PUSH)
        stdout_socket.connect(
            (f'tcp://127.0.0.1:{self.config["sockets"]["tapping_logging"]}'))

        informer_socket = context.socket(zmq.PUSH)
        informer_socket.connect(
            (f'tcp://127.0.0.1:{self.config["sockets"]["tapping_listener"]}'))

        try:
            filename = os.path.join(env.exec_dir, '.sos', 'interactive.sos')
            with open(filename, 'w') as script_file:
                script_file.write(self.code)

            cmd = f'sos run .sos/interactive.sos {self.args} -m tapping slave {self.config["slave_id"]} {self.config["sockets"]["tapping_logging"]} {self.config["sockets"]["tapping_listener"]} {self.config["sockets"]["tapping_controller"]}'
            ret_code = pexpect_run(
                cmd, shell=True, stdout_socket=stdout_socket)
            informer_socket.send_pyobj(
                {'msg_type': 'workflow_status',
                 'data': {
                     'cell_id': env.config['slave_id'],
                     'status': 'completed' if ret_code == 0 else 'failed'
                 }
                 })
        except Exception as e:
            stdout_socket.send_multipart([b'ERROR', str(e).encode()])
            informer_socket.send_pyobj({
                'msg_type': 'workflow_status',
                'data': {
                    'cell_id': env.config['slave_id'],
                    'status': 'failed',
                    'exception': str(e)
                }
            })
        finally:
            stdout_socket.LINGER = 0
            stdout_socket.close()
            informer_socket.LINGER = 0
            informer_socket.close()
            context.term()


# workflow queue that holds all workflow
g_workflow_queue = []

def run_next_workflow_in_queue():
    # execute the first available item
    global g_workflow_queue

    for idx, (cid, proc) in enumerate(g_workflow_queue):
        if proc is None:
            continue
        # this is ordered
        elif isinstance(proc, tuple):
            env.config['slave_id'] = cid
            executor = Tapped_Executor(*proc)
            executor.start()
            g_workflow_queue[idx][1] = executor
            break
        elif not (proc.is_alive() and psutil.pid_exists(proc.pid)):
            g_workflow_queue[idx][1] = None
            continue
        else:
            # if already running, do not submit new one
            break

def execute_pending_workflow(cell_ids, kernel):
    # we are giving a list of cell_ids because some cells might be removed
    # we use this list to clear workflow queue of removed cells
    for idx, (cid, proc) in enumerate(g_workflow_queue):
        if isinstance(proc, tuple) and cid not in cell_ids:
            g_workflow_queue[idx][1] = None
    run_next_workflow_in_queue()


def run_sos_workflow(code, raw_args='', kernel=None, workflow_mode=False):
    # when user asks to execute a cell as workflow. We either
    # execute the workflow or put it in queue
    global g_workflow_queue

    # if a cell already exist, remove previous pending job (a tuple)
    # completed job (dead process), or running job.
    if kernel.cell_id in [cid for cid, proc in g_workflow_queue if proc is not None]:
        cancel_workflow(kernel.cell_id, kernel)
    # put to the back
    g_workflow_queue.append([kernel.cell_id, (code, raw_args, env.config)])
    # in any case, we start with a pending status
    kernel.send_frontend_msg('workflow_status',
                             {
                                 'cell_id': kernel.cell_id,
                                 'status': 'pending',
                                 'index': len(g_workflow_queue)
                             })
    run_next_workflow_in_queue()

def cancel_workflow(cell_id, kernel):
    env.log_to_file(f'cancel {cell_id}')
    global g_workflow_queue
    kernel.send_frontend_msg('workflow_status', {
        'cell_id': cell_id,
        'status': 'aborted'
    })

    for idx, (cid, proc) in enumerate(g_workflow_queue):
        if cid != cell_id or proc is None:
            continue
        if not isinstance(proc, tuple) and \
            (proc.is_alive() and psutil.pid_exists(proc.pid)):
            from sos.executor_utils import kill_all_subprocesses
            kill_all_subprocesses(proc.pid, include_self=True)
            proc.terminate()
            if psutil.pid_exists(proc.pid):
                raise RuntimeError('Failed to kill workflow')
        g_workflow_queue[idx][1] = None
