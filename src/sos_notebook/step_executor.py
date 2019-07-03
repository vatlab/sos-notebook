#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import sys
import time

from sos.hosts import Host
from sos.step_executor import Base_Step_Executor
from sos.utils import env, short_repr
from sos.targets import sos_targets

class Interactive_Step_Executor(Base_Step_Executor):

    def __init__(self, step, mode='interactive'):
        super(Interactive_Step_Executor, self).__init__(step)
        self.run_mode = mode
        self.host = None

    def init_input_output_vars(self):
        # we keep these variables (which can be result of stepping through previous statements)
        # if no input and/or output statement is defined
        for key in ('step_input', '_depends', 'step_output', '_output', 'step_depends', '_depends'):
            if key not in env.sos_dict:
                env.sos_dict.set(key, sos_targets([]))
        if any(x[0] == ':' and x[1] == 'input' for x in self.step.statements):
            env.sos_dict.set('step_input', sos_targets([]))
            env.sos_dict.set('_input', sos_targets([]))
        if any(x[0] == ':' and x[1] == 'output' for x in self.step.statements):
            env.sos_dict.set('step_output', sos_targets([]))
            env.sos_dict.set('_output', sos_targets([]))
        env.sos_dict.pop('__default_output__', None)

    def submit_tasks(self, tasks):
        if not tasks:
            return
        if self.host is None:
            if 'queue' in env.sos_dict['_runtime']:
                queue = env.sos_dict['_runtime']['queue']
            elif env.config['default_queue']:
                queue = env.config['default_queue']
            else:
                queue = 'localhost'
            self.host = Host(queue)
        for task in tasks:
            self.host.submit_task(task)

    def wait_for_tasks(self, tasks, all_submitted):
        if not tasks:
            return {}
        # when we wait, the "outsiders" also need to see the tags etc
        # of the tasks so we have to write to the database. #156
        env.master_push_socket.send_pyobj(['commit_sig'])
        if all_submitted and 'shared' not in env.sos_dict['_runtime']:
            # if no shared and all taks have been submited return
            sys.exit(0)
        # turn this function to a generator to satisfy the interface, but do not
        # actually wait for any socket.
        yield None
        # wait till the executor responde
        if all(x == 'completed' for x in self.host.check_status(tasks)):
            if len(tasks) > 4:
                print('HINT: {} task{} completed: {}, {}, ..., {}'.format(
                    len(tasks), 's' if len(tasks) > 1 else '',
                    f"""<a onclick="task_info('{tasks[0]}', '{self.host.alias}')">{tasks[0][:4]}</a>""",
                    f"""<a onclick="task_info('{tasks[1]}', '{self.host.alias}')">{tasks[1][:4]}</a>""",
                    f"""<a onclick="task_info('{tasks[-1]}', '{self.host.alias}')">{tasks[-1][:4]}</a>"""
                ))
            else:
                print('HINT: {} task{} completed: {}'.format(
                    len(tasks), 's' if len(tasks) > 1 else '', ','.join([
                        f"""<a onclick="task_info('{x}', '{self.host.alias}')">{x[:4]}</a>"""
                        for x in tasks
                    ])))
            return self.host.retrieve_results(tasks)
        while True:
            res = self.host.check_status(tasks)
            if all(x not in ('submitted', 'pending', 'running') for x in res):
                #completed = [task for task, status in zip(tasks, res) if status == 'completed']
                return self.host.retrieve_results(tasks)
            time.sleep(0.1)

    def run(self):
        try:
            runner = Base_Step_Executor.run(self)
            yreq = next(runner)
            while True:
                yreq = runner.send(yreq)
        except StopIteration as e:
            return e.value

    def log(self, stage=None, msg=None):
        if stage == 'start':
            env.logger.debug('{} ``{}``: {}'.format(
                'Checking' if self.run_mode == 'dryrun' else 'Executing',
                self.step.step_name(), self.step.comment.strip()))
        elif stage == 'input':
            if env.sos_dict['step_input'] is not None:
                env.logger.debug('input:    ``{}``'.format(
                    short_repr(env.sos_dict['step_input'])))
        elif stage == 'output':
            if env.sos_dict['step_output'] is not None:
                env.logger.debug('output:   ``{}``'.format(
                    short_repr(env.sos_dict['step_output'])))

    def wait_for_subworkflows(self, workflow_results):
        '''Wait for results from subworkflows'''
        raise RuntimeError('Nested workflow is not supported in interactive mode')

    def handle_unknown_target(self, e):
        # wait for the clearnce of unknown target
        yield None
        raise e

    def verify_dynamic_targets(self, targets):
        raise RuntimeError('Dynamic targets are not supported in interative mode')
