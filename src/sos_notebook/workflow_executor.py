#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import datetime
import shlex
import sys

from sos.__main__ import get_run_parser
from sos.eval import SoS_exec
from sos.parser import SoS_Script
from sos.step_executor import PendingTasks
from sos.syntax import SOS_SECTION_HEADER
from sos.targets import (RemovedTarget, UnavailableLock,
                         UnknownTarget, sos_targets)
from sos.utils import _parse_error, env, get_traceback
from sos.workflow_executor import Base_Executor

from collections import defaultdict
from typing import Union, DefaultDict

from .step_executor import Interactive_Step_Executor


class Interactive_Executor(Base_Executor):
    '''Interactive executor called from by iPython Jupyter or Spyder'''

    def __init__(self, workflow=None, args=None, shared=None, config={}):
        # we actually do not have our own workflow, everything is passed from ipython
        # by nested = True we actually mean no new dictionary
        Base_Executor.__init__(self, workflow=workflow,
                               args=args, shared=shared, config=config)

    def reset_dict(self):
        # do not reset the entire env.sos_dict
        self.init_dict()
        # remove some variables because they would interfere with step analysis
        for key in ('_input', 'step_input'):
            env.sos_dict.pop(key, None)

    def run(self, targets=None, parent_pipe=None, my_workflow_id=None, mode=None):
        '''Execute a block of SoS script that is sent by iPython/Jupyer/Spyer
        The code can be simple SoS/Python statements, one SoS step, or more
        or more SoS workflows with multiple steps. This executor,
        1. adds a section header to the script if there is no section head
        2. execute the workflow in interactive mode, which is different from
           batch mode in a number of ways, which most notably without support
           for nested workflow.
        3. Optionally execute the workflow in preparation mode for debugging purposes.
        '''
        # if there is no valid code do nothing
        self.reset_dict()
        if not mode:
            mode = env.config.get('run_mode', 'interactive')
            # if user specified wrong mode with this executor, correct it.
            if mode == 'run':
                mode = 'interactive'
        env.config['run_mode'] = mode
        env.sos_dict.set('run_mode', mode)
        self.completed = defaultdict(int)

        # this is the result returned by the workflow, if the
        # last stement is an expression.
        wf_result = {'__workflow_id__': my_workflow_id,
                     'shared': {}, '__last_res__': None}

        # process step of the pipelinp
        if isinstance(targets, str):
            targets = [targets]
        #
        # if targets are specified and there are only signatures for them, we need
        # to remove the signature and really generate them
        if targets:
            targets = self.check_targets(targets)
            if len(targets) == 0:
                return wf_result

        #
        dag = self.initialize_dag(targets=targets)
        while True:
            # find any step that can be executed and run it, and update the DAT
            # with status.
            runnable = dag.find_executable()
            if runnable is None:
                break
            # find the section from runnable
            section = self.workflow.section_by_id(runnable._step_uuid)
            # clear existing keys, otherwise the results from some random result
            # might mess with the execution of another step that does not define input
            for k in ['__step_input__', '__default_output__', '__step_output__']:
                env.sos_dict.pop(k, None)
            # if the step has its own context
            env.sos_dict.quick_update(runnable._context)
            # execute section with specified input
            runnable._status = 'running'
            dag.save(env.config['output_dag'])
            try:
                # the global section might have parameter definition etc
                SoS_exec(section.global_def)
                executor = Interactive_Step_Executor(section, mode=mode)
                res = executor.run()
                self.step_completed(res, dag, runnable)
                wf_result['__last_res__'] = res['__last_res__']
            except (UnknownTarget, RemovedTarget) as e:
                self.handle_unknown_target(e, dag, runnable)
            except UnavailableLock as e:
                self.handle_unavailable_lock(e, dag, runnable)
            except PendingTasks as e:
                self.record_quit_status(e.tasks)
                raise
            # if the job is failed
            except Exception as e:
                runnable._status = 'failed'
                dag.save(env.config['output_dag'])
                raise
        self.finalize_and_report()
        wf_result['shared'] = {x: env.sos_dict[x]
                               for x in self.shared.keys() if x in env.sos_dict}
        wf_result['__completed__'] = self.completed
        return wf_result

#
# function runfile that is used by spyder to execute complete script
#


def runfile(script=None, raw_args='', wdir='.', code=None, kernel=None, **kwargs):
    # this has something to do with Prefix matching rule of parse_known_args
    #
    # That is to say
    #
    #   --rep 3
    #
    # would be parsed as
    #
    #   args.workflow=3, unknown --rep
    #
    # instead of
    #
    #   args.workflow=None, unknown --rep 3
    #
    # we then have to change the parse to disable args.workflow when
    # there is no workflow option.
    raw_args = shlex.split(raw_args) if isinstance(raw_args, str) else raw_args
    if (script is None and code is None) or '-h' in raw_args:
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

    # for reporting purpose
    sys.argv = ['%run'] + raw_args

    env.verbosity = args.verbosity

    dt = datetime.datetime.now().strftime('%m%d%y_%H%M')
    if args.__dag__ is None:
        args.__dag__ = f'workflow_{dt}.dot'
    elif args.__dag__ == '':
        args.__dag__ = None

    if args.__report__ is None:
        args.__report__ = f'workflow_{dt}.html'
    elif args.__report__ == '':
        args.__report__ = None

    if args.__remote__:
        from sos.utils import load_config_files
        cfg = load_config_files(args.__config__)
        env.sos_dict.set('CONFIG', cfg)

        # if executing on a remote host...
        from sos.hosts import Host
        host = Host(args.__remote__)
        #
        if script is None:
            if not code.strip():
                return
            script = os.path.join('.sos', '__interactive__.sos')
            with open(script, 'w') as s:
                s.write(code)

        # copy script to remote host...
        host.send_to_host(script)
        from sos.utils import remove_arg
        argv = shlex.split(raw_args) if isinstance(raw_args, str) else raw_args
        argv = remove_arg(argv, '-r')
        argv = remove_arg(argv, '-c')
        # execute the command on remote host
        try:
            with kernel.redirect_sos_io():
                ret = host._host_agent.run_command(['sos', 'run', script] + argv, wait_for_task=True,
                                                   realtime=True)
            if ret:
                kernel.send_response(kernel.iopub_socket, 'stream',
                                     dict(name='stderr',
                                          text=f'remote execution of workflow exited with code {ret}'))
        except Exception as e:
            if kernel:
                kernel.send_response(kernel.iopub_socket, 'stream',
                                     {'name': 'stdout', 'text': str(e)})
        return

    if args.__bin_dirs__:
        for d in args.__bin_dirs__:
            if d == '~/.sos/bin' and not os.path.isdir(os.path.expanduser(d)):
                os.makedirs(os.path.expanduser(d), exist_ok=True)
        os.environ['PATH'] = os.pathsep.join(
            [os.path.expanduser(x) for x in args.__bin_dirs__]) + os.pathsep + os.environ['PATH']

    # clear __step_input__, __step_output__ etc because there is
    # no concept of passing input/outputs across cells.
    env.sos_dict.set('__step_output__', sos_targets([]))
    for k in ['__step_input__', '__default_output__', 'step_input', 'step_output',
              'step_depends', '_input', '_output', '_depends']:
        env.sos_dict.pop(k, None)

    try:
        if script is None:
            if not code.strip():
                return
            if kernel is None:
                script = SoS_Script(content=code)
            else:
                if kernel._workflow_mode:
                    # in workflow mode, the content is sent by magics %run and %sosrun
                    script = SoS_Script(content=code)
                else:
                    # this is a scratch step...
                    # if there is no section header, add a header so that the block
                    # appears to be a SoS script with one section
                    if not any([SOS_SECTION_HEADER.match(line) or line.startswith('%from') or line.startswith('%include') for line in code.splitlines()]):
                        code = '[scratch_0]\n' + code
                        script = SoS_Script(content=code)
                    else:
                        if not kernel.cell_id:
                            kernel.send_frontend_msg('stream',
                                                     {'name': 'stdout', 'text': 'Workflow can only be executed with magic %run or %sosrun.'})
                        return
        else:
            script = SoS_Script(filename=script)
        workflow = script.workflow(
            args.workflow, use_default=not args.__targets__)
        env.config: DefaultDict[str, Union[None, bool, str]] = defaultdict(str)
        executor = Interactive_Executor(workflow, args=workflow_args, config={
            'config_file': args.__config__,
            'output_dag': args.__dag__,
            'output_report': args.__report__,
            'sig_mode': 'ignore' if args.dryrun else args.__sig_mode__,
            'default_queue': '' if args.__queue__ is None else args.__queue__,
            'wait_for_task': True if args.__wait__ is True or args.dryrun else (False if args.__no_wait__ else None),
            'resume_mode': kernel is not None and kernel._resume_execution,
            'run_mode': 'dryrun' if args.dryrun else 'interactive',
            'verbosity': args.verbosity,

            # wait if -w or in dryrun mode, not wait if -W, otherwise use queue default
            'max_procs': args.__max_procs__,
            'max_running_jobs': args.__max_running_jobs__,
            # for infomration and resume only
            'workdir': os.getcwd(),
            'script': "interactive",
            'workflow': args.workflow,
            'targets': args.__targets__,
            'bin_dirs': args.__bin_dirs__,
            'workflow_args': workflow_args
        })
        return executor.run(args.__targets__)['__last_res__']
    except PendingTasks:
        raise
    except SystemExit:
        # this happens because the executor is in resume mode but nothing
        # needs to be resumed, we simply pass
        return
    except Exception:
        if args.verbosity and args.verbosity > 2:
            sys.stderr.write(get_traceback())
        raise
    finally:
        env.config['sig_mode'] = 'ignore'
        env.verbosity = 1
