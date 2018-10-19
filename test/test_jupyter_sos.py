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

from sos.targets import file_target
from sos_notebook.test_utils import get_result, get_std_output, sos_kernel
from ipykernel.tests.utils import execute, wait_for_idle, TIMEOUT


class TestJupyterSoS(unittest.TestCase):
    #
    # Beacuse these tests would be called from sos/test, we
    # should switch to this directory so that some location
    # dependent tests could run successfully
    #
    def setUp(self):
        self.olddir = os.getcwd()
        if os.path.dirname(__file__):
            os.chdir(os.path.dirname(__file__))
        subprocess.call('sos remove -s', shell=True)

    def tearDown(self):
        os.chdir(self.olddir)

#     def testRerun(self):
#         with sos_kernel() as kc:
#             iopub = kc.iopub_channel
#             execute(kc=kc, code='''\
# %run
# parameter: a=10
# 
# [default]
# b = a
# ''')
#             wait_for_idle(kc)
#             #
#             execute(kc=kc, code='''\
# %rerun --a 20
# ''')
#             wait_for_idle(kc)
#             execute(kc=kc, code="b")
#             res = get_result(iopub)
#             self.assertEqual(res, 20)
# 
#     def testDAG(self):
#         with sos_kernel() as kc:
#             iopub = kc.iopub_channel
#             execute(kc=kc, code='''\
# %run
# [a]
# b=10
# 
# [default]
# sos_run('a')
# ''')
#             wait_for_idle(kc)
#             execute(kc=kc, code="b")
#             res = get_result(iopub)
#             self.assertEqual(res, 10)
# 
#     def testTarget(self):
#         for f in ['A1.txt', 'A2.txt', 'C2.txt', 'B2.txt', 'B1.txt', 'B3.txt', 'C1.txt', 'C3.txt', 'C4.txt']:
#             if file_target(f).exists():
#                 file_target(f).unlink()
#         #
#         #  A1 <- B1 <- B2 <- B3
#         #   |
#         #   |
#         #  \/
#         #  A2 <- B2 <- C1 <- C2 <- C4
#         #                    C3
#         #
#         script = '''\
# %run -t B1.txt -s force
# [A_1]
# input: 'B1.txt'
# output: 'A1.txt'
# run:
#     touch A1.txt
# 
# [A_2]
# depends:  'B2.txt'
# run:
#     touch A2.txt
# 
# [B1: provides='B1.txt']
# depends: 'B2.txt'
# run:
#     touch B1.txt
# 
# [B2: provides='B2.txt']
# depends: 'B3.txt', 'C1.txt'
# run:
#     touch B2.txt
# 
# [B3: provides='B3.txt']
# run:
#     touch B3.txt
# 
# [C1: provides='C1.txt']
# depends: 'C2.txt', 'C3.txt'
# run:
#     touch C1.txt
# 
# [C2: provides='C2.txt']
# depends: 'C4.txt'
# run:
#     touch C2.txt
# 
# [C3: provides='C3.txt']
# depends: 'C4.txt'
# run:
#     touch C3.txt
# 
# [C4: provides='C4.txt']
# run:
#     touch C4.txt
# 
#         '''
#         script2 = '''\
# import os
# fail = 0
# for f in ['A1.txt', 'A2.txt']:
#     fail += os.path.exists(f)
# for f in ['C2.txt', 'B2.txt', 'B1.txt', 'B3.txt', 'C1.txt', 'C3.txt', 'C4.txt']:
#     fail += not os.path.exists(f)
# fail
# '''
#         with sos_kernel() as kc:
#             iopub = kc.iopub_channel
#             execute(kc=kc, code=script)
#             wait_for_idle(kc)
#             execute(kc=kc, code=script2)
#             res = get_result(iopub)
#             self.assertEqual(res, 0)
# 
#     def testReverseSharedVariable(self):
#         '''Test shared variables defined in auxiliary steps'''
#         if file_target('a.txt').exists():
#             file_target('a.txt').unlink()
#         script = r'''
# %run B
# [A: shared='b', provides='a.txt']
# b = 1
# run:
#     touch a.txt
# 
# [B_1]
# depends: 'a.txt'
# 
# [B_2]
# print(b)
# 
# '''
#         with sos_kernel() as kc:
#             iopub = kc.iopub_channel
#             execute(kc=kc, code=script)
#             wait_for_idle(kc)
#             self.assertTrue(os.path.isfile('a.txt'))
#             execute(kc=kc, code="b")
#             res = get_result(iopub)
#             self.assertEqual(res, 1)


if __name__ == '__main__':
    unittest.main()
