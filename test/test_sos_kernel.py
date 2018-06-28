#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import sys
import unittest

from ipykernel.tests.utils import execute, wait_for_idle
from sos_notebook.test_utils import (get_display_data, get_result,
                                     get_std_output, sos_kernel)


class TestSoSKernel(unittest.TestCase):
    #
    # Beacuse these tests would be called from sos/test, we
    # should switch to this directory so that some location
    # dependent tests could run successfully
    #
    def setUp(self):
        self.olddir = os.getcwd()
        if os.path.dirname(__file__):
            os.chdir(os.path.dirname(__file__))

    def tearDown(self):
        os.chdir(self.olddir)

    def testAutoSharedVars(self):
        '''Test the sharing of variables automatically'''
        with sos_kernel() as kc:
            iopub = kc.iopub_channel
            execute(kc=kc, code="""\
sos_null = None
sos_num = 123
""")
            wait_for_idle(kc)
            execute(kc=kc, code="%use Python3")
            wait_for_idle(kc)
            execute(kc=kc, code="sos_num")
            res = get_display_data(iopub)
            self.assertEqual(res, '123')
            execute(kc=kc, code="sos_num = sos_num + 10")
            wait_for_idle(kc)
            execute(kc=kc, code="%use sos")
            wait_for_idle(kc)
            execute(kc=kc, code="sos_num")
            res = get_display_data(iopub)
            self.assertEqual(res, '133')

    def testMagicDict(self):
        '''Test %dict magic'''
        with sos_kernel() as kc:
            iopub = kc.iopub_channel
            execute(kc=kc, code="a=12345")
            wait_for_idle(kc)
            execute(kc=kc, code="%dict a")
            self.assertEqual(get_result(iopub)['a'], 12345)
            execute(kc=kc, code="%dict --keys")
            self.assertTrue('a' in get_result(iopub))
            execute(kc=kc, code="%dict --reset")
            wait_for_idle(kc)
            execute(kc=kc, code="%dict --keys --all")
            res = get_result(iopub)
            self.assertTrue('a' not in res)
            for key in ('run', 'expand_pattern'):
                self.assertTrue(key in res)

    def testShell(self):
        with sos_kernel() as kc:
            iopub = kc.iopub_channel
            execute(kc=kc, code="!echo ha ha")
            stdout, stderr = get_std_output(iopub)
            self.assertTrue('ha ha' in stdout, "GOT ERROR {}".format(stderr))
            self.assertEqual(stderr, '')

    def testCD(self):
        with sos_kernel() as kc:
            iopub = kc.iopub_channel
            execute(kc=kc, code="%cd ..")
            wait_for_idle(kc)
            execute(kc=kc, code="print(os.getcwd())")
            stdout, stderr = get_std_output(iopub)
            self.assertFalse(stdout.strip().endswith('jupyter'))
            self.assertEqual(stderr, '')
            execute(kc=kc, code="%cd jupyter")

    @unittest.skipIf(sys.platform == 'win32', 'AppVeyor does not support linux based docker')
    def testPullPush(self):
        '''Test set_options of sigil'''
        import random
        fname = os.path.expanduser("~/push_pull_{}.txt".format(random.randint(1, 100000)))
        with open(fname, 'w') as pp:
            pp.write('something')
        with sos_kernel() as kc:
            # create a data frame
            execute(kc=kc, code='%push {} --to docker -c ~/docker.yml'.format(fname))
            wait_for_idle(kc)
            os.remove(fname)
            self.assertFalse(os.path.isfile(fname))
            #
            execute(kc=kc, code='%pull {} --from docker -c ~/docker.yml'.format(fname))
            _, stderr = get_std_output(kc.iopub_channel)
            self.assertEqual(stderr, '', 'Expect no error, get {}'.format(stderr))
            self.assertTrue(os.path.isfile(fname))


if __name__ == '__main__':
    unittest.main()
