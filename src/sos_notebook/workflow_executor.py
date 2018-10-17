#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.
import re
import os
import datetime
import logging
from threading import Event
import time
import shlex
import sys
import zmq
import multiprocessing as mp

from sos.__main__ import get_run_parser
from sos.eval import SoS_exec
from sos.parser import SoS_Script
from sos.step_executor import PendingTasks
from sos.syntax import SOS_SECTION_HEADER
from sos.targets import (RemovedTarget, UnavailableLock,
                         UnknownTarget, sos_targets)
from sos.utils import _parse_error, env, get_traceback, pexpect_run, log_to_file
from sos.workflow_executor import Base_Executor
from sos.executor_utils import prepare_env
from sos.controller import Controller, connect_controllers, disconnect_controllers
from sos.section_analyzer import analyze_section

from collections import defaultdict
from typing import Union, DefaultDict

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
        'workflow_id': '0'
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
        # start a socket?
        context = zmq.Context()
        stdout_socket = context.socket(zmq.PUSH)
        stdout_socket.connect((f'tcp://127.0.0.1:{self.config["sockets"]["tapping_logging"]}'))
        try:
            while True:
                stdout_socket.send_multipart([b'INFO', b'HELLO'])
                log_to_file(f'alive and sent {stdout_socket.closed}')
                time.sleep(1)
            #
            # filename = os.path.join(env.exec_dir, '.sos', 'interactive.sos')
            # with open(filename, 'w') as script_file:
            #     script_file.write(self.code)
            #
            # cmd = f'sos run {filename} {raw_args} -m tapping {self.config["sockets"]["tapping_logging"]} {self.config["sockets"]["tapping_controller"]}'
            # pexpect_run(cmd, shell=True, stdout_socket=stdout_socket)
        except Exception as e:
            log_to_file(e)
            stdout_socket.send_multipart([b'ERROR', str(e).encode()])
        finally:
            stdout_socket.LINGER = 0
            stdout_socket.close()
            context.term()

def run_sos_workflow(code, raw_args='', kernel=None, workflow_mode=False):
    log_to_file(f'run sos workflow {env.config}')
    executor = Tapped_Executor(code, raw_args, env.config)
    executor.start()
