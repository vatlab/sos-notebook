#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

#
# NOTE: for some namespace reason, this test can only be tested using
# nose.
#
# % nosetests test_kernel.py
#
#
import os
import subprocess
import unittest

import nose.tools as nt
from ipykernel.tests.utils import execute, wait_for_idle
from sos_notebook.test_utils import KC, get_display_data, sos_kernel

TIMEOUT = 60


def long_execute(code='', kc=None, **kwargs):
    """wrapper for doing common steps for validating an execution request"""
    from ipykernel.tests.test_message_spec import validate_message
    if kc is None:
        kc = KC
    msg_id = kc.execute(code=code, **kwargs)
    reply = kc.get_shell_msg(timeout=TIMEOUT)
    validate_message(reply, 'execute_reply', msg_id)
    busy = kc.get_iopub_msg(timeout=TIMEOUT)
    validate_message(busy, 'status', msg_id)
    nt.assert_equal(busy['content']['execution_state'], 'busy')

    if not kwargs.get('silent'):
        execute_input = kc.get_iopub_msg(timeout=TIMEOUT)
        validate_message(execute_input, 'execute_input', msg_id)
        nt.assert_equal(execute_input['content']['code'], code)

    return msg_id, reply['content']


class TestJupyterTasks(unittest.TestCase):

    def testForceTask(self):
        '''Test the execution of tasks with -s force'''
        # FIXME This test will not work because there is no frontend in the
        # test so there is no way to pass the --resume option to the kernel
        # to actually rerun the scripts.
        with sos_kernel() as kc:
            # the cell will actually be executed several times
            # with automatic-reexecution
            code = """\
%set -v1
%run -s force
[10]
input: for_each={'i': range(1)}
task:
run: expand=True
   echo this is "{i}"
   sleep {i}

[20]
input: for_each={'i': range(2)}
task:
run: expand=True
   echo this aa is "{i}"
   sleep {i}

"""
            # these should be automatically rerun by the frontend
            long_execute(kc=kc, code=code)
            wait_for_idle(kc)

#     def testPendingTask(self):
#         '''Test the execution of tasks with -s force'''
#         with sos_kernel() as kc:
#             # the cell will actually be executed several times
#             # with automatic-reexecution
#             code = """\
# input: for_each={'i': range(2)}
# task:
# run: expand=True
#    echo this is jupyter pending test "{i}"
#    sleep  {10+i}
# 
# """
#             # these should be automatically rerun by the frontend
#             execute(kc=kc, code=code)
#             wait_for_idle(kc)
#             # check for task?
#             execute(kc=kc, code='%tasks')
#             res = get_display_data(kc.iopub_channel, 'text/html')
#             # get IDs
#             # table_localhost_ac755352394584f797cebddf2c0b8ca7"
#             tid = res.split('table_localhost_')[-1].split('"')[0]
#             # now we have the tid, we can check task info
#             execute(kc=kc, code='%taskinfo ' + tid)
#             res = get_display_data(kc.iopub_channel, 'text/html')
#             self.assertTrue(tid in res)
#             # there should be two tasks
#             #lines = subprocess.check_output(['sos', 'status']).decode().splitlines()
#             # for duo-core machine, perhaps only one job is running.
#             #self.assertGreaterEqual(len(lines), 1)


if __name__ == '__main__':
    unittest.main()
