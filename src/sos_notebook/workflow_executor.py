#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import keyword
import os
import datetime
import shlex
import subprocess
import sys
import tempfile
import time

from sos.__main__ import get_run_parser
from sos._version import __version__
from sos.eval import SoS_exec
from sos.parser import SoS_Script
from sos.step_executor import PendingTasks
from sos.syntax import SOS_SECTION_HEADER
from sos.targets import (RemovedTarget, UnavailableLock, BaseTarget,
                         UnknownTarget, file_target, path, sos_targets)
from sos.utils import _parse_error, env, get_traceback, load_config_files
from sos.workflow_executor import Base_Executor, __null_func__
from sos.report import workflow_report, render_report

from collections import defaultdict
from typing import Union, DefaultDict

from .step_executor import Interactive_Step_Executor


class Interactive_Executor(Base_Executor):
    '''Interactive executor called from by iPython Jupyter or Spyder'''

    def __init__(self, workflow=None, args=None, shared=None, config=None):
        # we actually do not have our own workflow, everything is passed from ipython
        # by nested = True we actually mean no new dictionary
        Base_Executor.__init__(self, workflow=workflow,
                               args=args, shared=shared, config=config)

    def reset_dict(self):
        env.sos_dict.set('__null_func__', __null_func__)
        env.sos_dict.set('SOS_VERSION', __version__)
        env.sos_dict.set('__args__', self.args)
        env.sos_dict.set('workflow_id', self.md5)

        self._base_symbols = set(dir(__builtins__)) | set(
            env.sos_dict['sos_symbols_']) | set(keyword.kwlist)
        self._base_symbols -= {'dynamic', 'sos_run'}

        # load configuration files
        cfg = load_config_files(env.config['config_file'])
        # if check_readonly is set to True, allow checking readonly vars
        if cfg.get('sos', {}).get('change_all_cap_vars', None) is not None:
            if cfg['sos']['change_all_cap_vars'] not in ('warning', 'error'):
                env.logger.error(
                    f'Configuration sos.change_all_cap_vars can only be warning or error: {cfg["sos"]["change_all_cap_vars"]} provided')
            else:
                env.sos_dict._change_all_cap_vars = cfg['sos']['change_all_cap_vars']
        env.sos_dict.set('CONFIG', cfg)
        # set config to CONFIG
        file_target('config.yml').remove('both')

        # remove some variables because they would interfere with step analysis
        for key in ('_input', 'step_input'):
            env.sos_dict.pop(key, None)

        env.sos_dict.quick_update(self.shared)

        if isinstance(self.args, dict):
            for key, value in self.args.items():
                if not key.startswith('__'):
                    env.sos_dict.set(key, value)

    def run(self, targets=None, parent_pipe=None, my_workflow_id=None, mode='run'):
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
        self.completed = defaultdict(int)

        # this is the result returned by the workflow, if the
        # last stement is an expression.
        last_res = None

        # process step of the pipelinp
        if isinstance(targets, str):
            targets = [targets]
        #
        # if targets are specified and there are only signatures for them, we need
        # to remove the signature and really generate them
        if targets:
            for t in targets:
                if file_target(t).target_exists('target'):
                    env.logger.debug(f'Target {t} already exists')
                elif file_target(t).target_exists('signature'):
                    env.logger.debug(f'Re-generating {t}')
                    file_target(t).remove('signature')
            targets = [x for x in targets if not file_target(
                x).target_exists('target')]
        #
        dag = self.initialize_dag(targets=targets)
        while True:
            # find any step that can be executed and run it, and update the DAT
            # with status.
            runnable = dag.find_executable()
            if runnable is None:
                # no runnable
                # dag.show_nodes()
                break
            # find the section from runnable
            section = self.workflow.section_by_id(runnable._step_uuid)
            #
            # this is to keep compatibility of dag run with sequential run because
            # in sequential run, we evaluate global section of each step in
            # order to determine values of options such as skip.
            # The consequence is that global definitions are available in
            # SoS namespace.
            try:
                SoS_exec(section.global_def)
            except Exception as e:
                if env.verbosity > 2:
                    sys.stderr.write(get_traceback())
                raise RuntimeError(
                    f'Failed to execute statements\n"{section.global_def}"\n{e}')

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
                executor = Interactive_Step_Executor(section)
                res = executor.run()
                for k, v in res.items():
                    env.sos_dict.set(k, v)

                for k, v in res['__completed__'].items():
                    self.completed[k] += v
                if res['__completed__']['__substep_completed__'] == 0:
                    self.completed['__step_skipped__'] += 1
                else:
                    self.completed['__step_completed__'] += 1

                last_res = res['__last_res__']
                # set context to the next logic step.
                for edge in dag.out_edges(runnable):
                    node = edge[1]
                    # if node is the logical next step...
                    if node._node_index is not None and runnable._node_index is not None:
                        # and node._node_index == runnable._node_index + 1:
                        node._context.update(env.sos_dict.clone_selected_vars(
                            node._context['__signature_vars__'] | node._context['__environ_vars__']
                            | {'_input', '__step_output__', '__default_output__', '__args__'}))
                    node._context['__completed__'].append(res['__step_name__'])
                runnable._status = 'completed'
                dag.save(env.config['output_dag'])
            except (UnknownTarget, RemovedTarget) as e:
                runnable._status = None
                dag.save(env.config['output_dag'])
                target = e.target
                if dag.regenerate_target(target):
                    # runnable._depends_targets.append(target)
                    # dag._all_dependent_files[target].append(runnable)
                    dag.build(self.workflow.auxiliary_sections)
                    #
                    cycle = dag.circular_dependencies()
                    if cycle:
                        raise RuntimeError(
                            f'Circular dependency detected {cycle} after regeneration. It is likely a later step produces input of a previous step.')
                else:
                    if self.resolve_dangling_targets(dag, sos_targets(target)) == 0:
                        raise RuntimeError(
                            f'Failed to regenerate or resolve {target}{dag.steps_depending_on(target, self.workflow)}.')
                    if runnable._depends_targets.determined():
                        runnable._depends_targets.extend(target)
                    if runnable not in dag._all_dependent_files[target]:
                        dag._all_dependent_files[target].append(runnable)
                    dag.build(self.workflow.auxiliary_sections)
                    #
                    cycle = dag.circular_dependencies()
                    if cycle:
                        raise RuntimeError(
                            f'Circular dependency detected {cycle}. It is likely a later step produces input of a previous step.')
                dag.save(env.config['output_dag'])
            except UnavailableLock as e:
                runnable._status = 'pending'
                dag.save(env.config['output_dag'])
                runnable._signature = (e.output, e.sig_file)
                env.logger.debug(
                    f'Waiting on another process for step {section.step_name()}')
            except PendingTasks as e:
                self.record_quit_status(e.tasks)
                raise
            # if the job is failed
            except Exception as e:
                runnable._status = 'failed'
                dag.save(env.config['output_dag'])
                raise
        if self.md5:
            env.logger.debug(
                f'Workflow {self.workflow.name} (ID={self.md5}) is executed successfully.')
            with workflow_report() as sig:
                workflow_info = {
                    'end_time': time.time(),
                    'stat': dict(self.completed),
                }
                if env.config['output_dag'] and env.config['master_id'] == self.md5:
                    workflow_info['dag'] = env.config['output_dag']
                sig.write(f'workflow\t{self.md5}\t{workflow_info}\n')
            if env.config['output_report'] and env.sos_dict.get('workflow_id'):
                # if this is the outter most workflow
                render_report(env.config['output_report'],
                              env.sos_dict.get('workflow_id'))
        # remove task pending status if the workflow is completed normally
        try:
            wf_status = os.path.join(os.path.expanduser(
                '~'), '.sos', self.md5 + '.status')
            if os.path.isfile(wf_status):
                os.remove(wf_status)
        except Exception as e:
            env.logger.warning(f'Failed to clear workflow status file: {e}')
        return last_res

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
        import fasteners
        for d in args.__bin_dirs__:
            if d == '~/.sos/bin' and not os.path.isdir(os.path.expanduser(d)):
                os.makedirs(os.path.expanduser(d), exist_ok = True)
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
            'sig_mode': args.__sig_mode__,
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
        return executor.run(args.__targets__)
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
        env.verbosity = 2
