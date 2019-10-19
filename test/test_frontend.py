#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import time
import unittest

from ipykernel.tests.utils import execute, wait_for_idle
from sos_notebook.test_utils import flush_channels, sos_kernel, NotebookTest
from selenium.webdriver.common.keys import Keys


class TestFrontEnd(NotebookTest):

    def test_toggle_console(self, notebook):
        time.sleep(2)
        assert notebook.is_console_panel_open()
        notebook.toggle_console_panel()
        time.sleep(2)
        assert not notebook.is_console_panel_open()
        notebook.toggle_console_panel()
        time.sleep(2)
        assert notebook.is_console_panel_open()

    def test_run_in_console(self, notebook):
        idx = notebook.call("print(1)", kernel="SoS")
        notebook.execute_cell(idx, in_console=True)
        # the latest history cell
        assert "1" == notebook.get_cell_output(-1, in_console=True)

        # if the cell is non-SoS, the console should also change kernel
        idx = notebook.call("cat(123)", kernel="R")
        notebook.execute_cell(idx, in_console=True)
        # the latest history cell
        assert "123" == notebook.get_cell_output(-1, in_console=True)

        idx = notebook.call("print(12345)", kernel="SoS")
        notebook.execute_cell(idx, in_console=True)
        # the latest history cell
        assert "12345" == notebook.get_cell_output(-1, in_console=True)

    def test_run_directly_in_console(self, notebook):
        notebook.edit_prompt_cell('print("haha")', kernel='SoS', execute=True)
        assert "haha" == notebook.get_cell_output(-1, in_console=True)

        notebook.edit_prompt_cell('cat("haha2")', kernel="R", execute=True)
        assert "haha2" == notebook.get_cell_output(-1, in_console=True)

    def test_history_in_console(self, notebook):
        notebook.edit_prompt_cell("a = 1", execute=True)
        assert "" == notebook.get_prompt_content()
        notebook.edit_prompt_cell("b <- 2", kernel="R", execute=True)
        assert "" == notebook.get_prompt_content()
        notebook.prompt_cell.send_keys(Keys.UP)
        assert "b <- 2" == notebook.get_prompt_content()
        notebook.prompt_cell.send_keys(Keys.UP)
        assert "a = 1" == notebook.get_prompt_content()
        # FIXME: down keys does not work, perhaps because the cell is not focused and
        # the first step would be jumping to the end of the line
        notebook.prompt_cell.send_keys(Keys.DOWN)
        notebook.prompt_cell.send_keys(Keys.DOWN)
        #  assert 'b <- 2' == notebook.get_prompt_content()

    def test_clear_history(self, notebook):
        notebook.edit_prompt_cell("a = 1", execute=True)
        notebook.edit_prompt_cell("b <- 2", kernel="R", execute=True)
        # use "clear" to clear all panel cells
        notebook.edit_prompt_cell("clear", kernel="SoS", execute=False)
        # we cannot wait for the completion of the cell because the cells
        # will be cleared
        notebook.prompt_cell.send_keys(Keys.CONTROL, Keys.ENTER)
        assert not notebook.panel_cells

    def test_switch_kernel(self, notebook):
        kernels = notebook.get_kernel_list()
        assert "SoS" in kernels
        assert "R" in kernels
        backgroundColor = {
            "SoS": [0, 0, 0],
            "R": [220, 220, 218],
            "python3": [255, 217, 26],
        }

        # test change to R kernel by click
        notebook.select_kernel(index=0, kernel_name="R", by_click=True)
        # check background color for R kernel
        assert backgroundColor["R"], notebook.get_input_backgroundColor(0)

        # the cell keeps its color after evaluation
        notebook.edit_cell(
            index=0,
            content="""\
            %preview -n rn
            rn <- rnorm(5)
            """,
            render=True,
        )
        output = notebook.get_cell_output(0)
        assert "rn" in output and "num" in output
        assert backgroundColor["R"], notebook.get_output_backgroundColor(0)

        # test $get and shift to SoS kernel
        idx = notebook.call(
            """\
            %get rn --from R
            len(rn)
            """,
            kernel="SoS",
        )
        assert backgroundColor["SoS"], notebook.get_input_backgroundColor(idx)
        assert "5" in notebook.get_cell_output(idx)

        # switch to python3 kernel
        idx = notebook.call(
            """\
            %use Python3
            """,
            kernel="SoS",
        )
        assert backgroundColor["python3"] == notebook.get_input_backgroundColor(
            idx)

        notebook.append_cell("")
        assert backgroundColor["python3"] == notebook.get_input_backgroundColor(
            idx)

    # def testInterrupt(self, notebook):
    #     # switch to python3 kernel
    #     from textwrap import dedent
    #     from selenium.webdriver.common.by import By
    #     from selenium.webdriver import ActionChains

    #     import time
    #     index = len(notebook.cells)
    #     notebook.add_cell(
    #         index=index - 1, cell_type="code", content=dedent(
    #             """\
    #             import time
    #             while True:
    #                 time.sleep(1)
    #             """,
    #         ))
    #     notebook.select_kernel(index=index, kernel_name='SoS', by_click=True)
    #     notebook._focus_cell(index)
    #     notebook.current_cell.send_keys(Keys.CONTROL, Keys.ENTER)
    #     time.sleep(2)

    #     top_menu = notebook.browser.find_element_by_id("kernel_menu")
    #     ActionChains(notebook.browser).move_to_element(top_menu).click().perform()
    #     int_menu = notebook.browser.find_element_by_id("int_kernel").find_elements_by_tag_name('a')[0]
    #     ActionChains(notebook.browser).move_to_element(int_menu).click().perform()
    #     notebook._wait_for_done(index, expect_error=True)


def get_completions(kc, text):
    flush_channels()
    kc.complete(text, len(text))
    reply = kc.get_shell_msg(timeout=2)
    return reply["content"]


def inspect(kc, name, pos=0):
    flush_channels()
    kc.inspect(name, pos)
    reply = kc.get_shell_msg(timeout=2)
    return reply["content"]


def is_complete(kc, code):
    flush_channels()
    kc.is_complete(code)
    reply = kc.get_shell_msg(timeout=2)
    return reply["content"]


class TestKernelInteraction(unittest.TestCase):

    def testInspector(self):
        with sos_kernel() as kc:
            # match magics
            self.assertTrue("%get " in get_completions(kc, "%g")["matches"])
            self.assertTrue("%get " in get_completions(kc, "%")["matches"])
            self.assertTrue("%with " in get_completions(kc, "%w")["matches"])
            # path complete
            self.assertGreater(len(get_completions(kc, "!ls ")["matches"]), 0)
            self.assertEqual(
                len(get_completions(kc, "!ls SOMETHING")["matches"]), 0)
            #
            wait_for_idle(kc)
            # variable complete
            execute(kc=kc, code="alpha=5")
            wait_for_idle(kc)
            execute(kc=kc, code="%use Python3")
            wait_for_idle(kc)
            self.assertTrue("alpha" in get_completions(kc, "al")["matches"])
            self.assertTrue("all(" in get_completions(kc, "al")["matches"])
            # for no match
            self.assertEqual(
                len(get_completions(kc, "alphabetatheta")["matches"]), 0)
            # get with all variables in
            self.assertTrue("alpha" in get_completions(kc, "%get ")["matches"])
            self.assertTrue(
                "alpha" in get_completions(kc, "%get al")["matches"])
            # with use and restart has kernel name
            self.assertTrue(
                "Python3" in get_completions(kc, "%with ")["matches"])
            self.assertTrue(
                "Python3" in get_completions(kc, "%use ")["matches"])
            self.assertTrue(
                "Python3" in get_completions(kc, "%shutdown ")["matches"])
            self.assertTrue(
                "Python3" in get_completions(kc, "%shutdown ")["matches"])
            self.assertTrue(
                "Python3" in get_completions(kc, "%use Py")["matches"])
            #
            self.assertEqual(
                len(get_completions(kc, "%use SOME")["matches"]), 0)
            #
            wait_for_idle(kc)
            execute(kc=kc, code="%use SoS")
            wait_for_idle(kc)

    def testCompleter(self):
        with sos_kernel() as kc:
            # match magics
            ins_print = inspect(kc, "print")["data"]["text/plain"]
            self.assertTrue("print" in ins_print,
                            "Returned: {}".format(ins_print))
            wait_for_idle(kc)
            #
            # keywords
            ins_depends = inspect(kc, "depends:")["data"]["text/plain"]
            self.assertTrue("dependent targets" in ins_depends,
                            "Returned: {}".format(ins_depends))
            wait_for_idle(kc)
            #
            execute(kc=kc, code="alpha=5")
            wait_for_idle(kc)
            execute(kc=kc, code="%use Python3")
            wait_for_idle(kc)
            # action
            ins_run = inspect(kc, "run:")["data"]["text/plain"]
            self.assertTrue("sos.actions" in ins_run,
                            "Returned: {}".format(ins_run))
            wait_for_idle(kc)
            #
            ins_alpha = inspect(kc, "alpha")["data"]["text/plain"]
            self.assertTrue("5" in ins_alpha, "Returned: {}".format(ins_alpha))
            wait_for_idle(kc)
            for magic in ("get", "run", "sosrun"):
                ins_magic = inspect(kc, "%" + magic, 2)["data"]["text/plain"]
                self.assertTrue("usage: %" + magic in ins_magic,
                                "Returned: {}".format(ins_magic))
            wait_for_idle(kc)
            execute(kc=kc, code="%use SoS")
            wait_for_idle(kc)

    def testIsComplete(self):
        with sos_kernel() as kc:
            # match magics
            status = is_complete(kc, "prin")
            self.assertEqual(status["status"], "complete")
            #
            status = is_complete(kc, "a=1")
            self.assertEqual(status["status"], "complete")
            #
            status = is_complete(kc, "")
            self.assertEqual(status["status"], "complete")
            # the status seems to be version dependent on ipython
            #status = is_complete(kc, "input:\n a=1,")
            #self.assertEqual(status["status"], "complete")
            #
            #status = is_complete(kc, "parameter: a=1,")
            #self.assertEqual(status["status"], "complete")
            #
            status = is_complete(kc, "%dict -r")
            self.assertEqual(status["status"], "complete")

            wait_for_idle(kc)

if __name__ == "__main__":
    unittest.main()
