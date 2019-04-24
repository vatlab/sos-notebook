#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.


import unittest
from textwrap import dedent

from ipykernel.tests.utils import execute, wait_for_idle
from sos_notebook.test_utils import flush_channels, sos_kernel, NotebookTest

import time

class TestFrontEnd(NotebookTest):
    def test_sidepanel(self, notebook):
        time.sleep(2)
        assert True == notebook.get_sidePanel()
        notebook.toggle_sidePanel()
        time.sleep(2)
        assert False == notebook.get_sidePanel()
        notebook.toggle_sidePanel()
        time.sleep(2)
        assert True == notebook.get_sidePanel()

        #command = "print(1)"
        #notebook.edit_cell(index=0, content=command, render=False)
        #notebook.execute_cell(cell_or_index=0, inPanel=True)
        # assert "1"==notebook.get_cell_output(index=1,inPanel=True)

        # FIXME
        # notebook.shift_console_kernel(kernel_name="python3", by_click=True)
        # content = "print(2)"
        # notebook.edit_panel_input(content=content)


    def test_switch_kernel(self, notebook):
        kernels = notebook.get_kernel_list()
        assert "SoS" in kernels
        assert "R" in kernels
        backgroundColor = {"SoS": [0, 0, 0],
                        "R": [220, 220, 218],
                        "python3": [255, 217, 26]}

        # test shift to R kernel by click
        notebook.shift_kernel(index=0, kernel_name="R", by_click=True)
        # check background color for R kernel
        assert all([a == b] for a, b in zip(backgroundColor["R"],
                                            notebook.get_input_backgroundColor(0)))

        # the cell keeps its color after evaluation
        notebook.edit_cell(index=0, content=dedent("""\
            %preview -n rn[1:3]
            rn <- rnorm(50)
            """), render=True)
        assert "rn[1:3]" in notebook.get_cell_output(index=0)
        assert all([a == b] for a, b in zip(backgroundColor["R"],
                                            notebook.get_output_backgroundColor(0)))

        # test $get and shift to SoS kernel
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %get rn --from R
            len(rn)
            '''), kernel='SoS')
        assert all([a == b] for a, b in zip(backgroundColor["SoS"],
                                            notebook.get_input_backgroundColor(idx)))
        assert "50" in notebook.get_cell_output(index=idx)

        # switch to python3 kernel
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %use Python3
            '''), kernel='SoS')
        assert all([a == b] for a, b in zip(backgroundColor["python3"],
                                            notebook.get_input_backgroundColor(idx)))
        notebook.append("")
        assert all([a == b] for a, b in zip(backgroundColor["python3"],
                                            notebook.get_input_backgroundColor(idx)))


def get_completions(kc, text):
    flush_channels()
    kc.complete(text, len(text))
    reply = kc.get_shell_msg(timeout=2)
    return reply['content']


def inspect(kc, name, pos=0):
    flush_channels()
    kc.inspect(name, pos)
    reply = kc.get_shell_msg(timeout=2)
    return reply['content']


def is_complete(kc, code):
    flush_channels()
    kc.is_complete(code)
    reply = kc.get_shell_msg(timeout=2)
    return reply['content']


class TestKernelInteraction(unittest.TestCase):
    def testInspector(self):
        with sos_kernel() as kc:
            # match magics
            self.assertTrue('%get ' in get_completions(kc, '%g')['matches'])
            self.assertTrue('%get ' in get_completions(kc, '%')['matches'])
            self.assertTrue('%with ' in get_completions(kc, '%w')['matches'])
            # path complete
            self.assertGreater(len(get_completions(kc, '!ls ')['matches']), 0)
            self.assertEqual(
                len(get_completions(kc, '!ls SOMETHING')['matches']), 0)
            #
            wait_for_idle(kc)
            # variable complete
            execute(kc=kc, code='alpha=5')
            wait_for_idle(kc)
            execute(kc=kc, code='%use Python3')
            wait_for_idle(kc)
            self.assertTrue('alpha' in get_completions(kc, 'al')['matches'])
            self.assertTrue('all(' in get_completions(kc, 'al')['matches'])
            # for no match
            self.assertEqual(
                len(get_completions(kc, 'alphabetatheta')['matches']), 0)
            # get with all variables in
            self.assertTrue('alpha' in get_completions(kc, '%get ')['matches'])
            self.assertTrue('alpha' in get_completions(
                kc, '%get al')['matches'])
            # with use and restart has kernel name
            self.assertTrue('Python3' in get_completions(
                kc, '%with ')['matches'])
            self.assertTrue('Python3' in get_completions(
                kc, '%use ')['matches'])
            self.assertTrue('Python3' in get_completions(
                kc, '%shutdown ')['matches'])
            self.assertTrue('Python3' in get_completions(
                kc, '%shutdown ')['matches'])
            self.assertTrue('Python3' in get_completions(
                kc, '%use Py')['matches'])
            #
            self.assertEqual(
                len(get_completions(kc, '%use SOME')['matches']), 0)
            #
            wait_for_idle(kc)
            execute(kc=kc, code='%use SoS')
            wait_for_idle(kc)

    def testCompleter(self):
        with sos_kernel() as kc:
            # match magics
            ins_print = inspect(kc, 'print')['data']['text/plain']
            self.assertTrue('print' in ins_print,
                            'Returned: {}'.format(ins_print))
            wait_for_idle(kc)
            #
            # keywords
            ins_depends = inspect(kc, 'depends:')['data']['text/plain']
            self.assertTrue('dependent targets' in ins_depends,
                            'Returned: {}'.format(ins_depends))
            wait_for_idle(kc)
            #
            execute(kc=kc, code='alpha=5')
            wait_for_idle(kc)
            execute(kc=kc, code='%use Python3')
            wait_for_idle(kc)
            # action
            ins_run = inspect(kc, 'run:')['data']['text/plain']
            self.assertTrue('sos.actions' in ins_run,
                            'Returned: {}'.format(ins_run))
            wait_for_idle(kc)
            #
            ins_alpha = inspect(kc, 'alpha')['data']['text/plain']
            self.assertTrue('5' in ins_alpha, 'Returned: {}'.format(ins_alpha))
            wait_for_idle(kc)
            for magic in ('get', 'run', 'set', 'sosrun', 'toc'):
                ins_magic = inspect(kc, '%' + magic, 2)['data']['text/plain']
                self.assertTrue('usage: %' + magic in ins_magic,
                                'Returned: {}'.format(ins_magic))
            wait_for_idle(kc)
            execute(kc=kc, code='%use SoS')
            wait_for_idle(kc)

    def testIsComplete(self):
        with sos_kernel() as kc:
            # match magics
            status = is_complete(kc, 'prin')
            self.assertEqual(status['status'], 'incomplete')
            #
            status = is_complete(kc, 'a=1')
            self.assertEqual(status['status'], 'incomplete')
            #
            status = is_complete(kc, '')
            self.assertEqual(status['status'], 'complete')
            #
            status = is_complete(kc, 'input:\n a=1,')
            self.assertEqual(status['status'], 'incomplete')
            #
            status = is_complete(kc, '%dict -r')
            self.assertEqual(status['status'], 'complete')
            wait_for_idle(kc)


if __name__ == '__main__':
    unittest.main()
