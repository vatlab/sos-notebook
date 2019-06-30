#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

#
# NOTE: for some namespace reason, this test can only be tested using
# nose.

import atexit
import os
import re
import time
from sys import platform
from textwrap import dedent

from ipykernel.tests import utils as test_utils
#
#
from contextlib import contextmanager
from queue import Empty

import pytest

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

pjoin = os.path.join

test_utils.TIMEOUT = 60

KM = None
KC = None


@contextmanager
def sos_kernel():
    """Context manager for the global kernel instance
    Should be used for most kernel tests
    Returns
    -------
    kernel_client: connected KernelClient instance
    """
    yield start_sos_kernel()


def flush_channels(kc=None):
    """flush any messages waiting on the queue"""

    if kc is None:
        kc = KC
    for channel in (kc.shell_channel, kc.iopub_channel):
        while True:
            try:
                channel.get_msg(block=True, timeout=0.1)
            except Empty:
                break
            # do not validate message because SoS has special sos_comm
            # else:
            #    validate_message(msg)


def start_sos_kernel():
    """start the global kernel (if it isn't running) and return its client"""
    global KM, KC
    if KM is None:
        KM, KC = test_utils.start_new_kernel(kernel_name='sos')
        atexit.register(stop_sos_kernel)
    else:
        flush_channels(KC)
    return KC


def stop_sos_kernel():
    """Stop the global shared kernel instance, if it exists"""
    global KM, KC
    KC.stop_channels()
    KC = None
    if KM is None:
        return
    KM.shutdown_kernel(now=False)
    KM = None


def get_result(iopub):
    """retrieve result from an execution"""
    result = None
    while True:
        msg = iopub.get_msg(block=True, timeout=1)
        msg_type = msg['msg_type']
        content = msg['content']
        if msg_type == 'status' and content['execution_state'] == 'idle':
            # idle message signals end of output
            break
        elif msg['msg_type'] == 'execute_result':
            result = content['data']
        elif msg['msg_type'] == 'display_data':
            result = content['data']
        else:
            # other output, ignored
            pass
    # text/plain can have fronzen dict, this is ok,
    from numpy import array, matrix, uint8
    # suppress pyflakes warning
    array
    matrix
    uint8

    # it can also have dict_keys, we will have to redefine it

    def dict_keys(args):
        return args

    if result is None:
        return None
    else:
        return eval(result['text/plain'])


def get_display_data(iopub, data_type='text/plain'):
    """retrieve display_data from an execution from subkernel
    because subkernel (for example irkernel) does not return
    execution_result
    """
    result = None
    while True:
        msg = iopub.get_msg(block=True, timeout=1)
        msg_type = msg['msg_type']
        content = msg['content']
        if msg_type == 'status' and content['execution_state'] == 'idle':
            # idle message signals end of output
            break
        elif msg['msg_type'] == 'display_data':
            if isinstance(data_type, str):
                if data_type in content['data']:
                    result = content['data'][data_type]
            else:
                for dt in data_type:
                    if dt in content['data']:
                        result = content['data'][dt]
        # some early version of IRKernel still passes execute_result
        elif msg['msg_type'] == 'execute_result':
            result = content['data']['text/plain']
    return result


def clear_channels(iopub):
    """assemble stdout/err from an execution"""
    while True:
        msg = iopub.get_msg(block=True, timeout=1)
        msg_type = msg['msg_type']
        content = msg['content']
        if msg_type == 'status' and content['execution_state'] == 'idle':
            # idle message signals end of output
            break


def get_std_output(iopub):
    '''Obtain stderr and remove some unnecessary warning from
    https://github.com/jupyter/jupyter_client/pull/201#issuecomment-314269710'''
    stdout, stderr = test_utils.assemble_output(iopub)
    return stdout, '\n'.join([
        x for x in stderr.splitlines() if 'sticky' not in x and
        'RuntimeWarning' not in x and 'communicator' not in x
    ])


def wait_for_selector(browser,
                      selector,
                      timeout=10,
                      visible=False,
                      single=False):
    wait = WebDriverWait(browser, timeout)
    if single:
        if visible:
            conditional = EC.visibility_of_element_located
        else:
            conditional = EC.presence_of_element_located
    else:
        if visible:
            conditional = EC.visibility_of_all_elements_located
        else:
            conditional = EC.presence_of_all_elements_located
    return wait.until(conditional((By.CSS_SELECTOR, selector)))


def wait_for_tag(driver,
                 tag,
                 timeout=10,
                 visible=False,
                 single=False,
                 wait_for_n=1):
    if wait_for_n > 1:
        return _wait_for_multiple(driver, By.TAG_NAME, tag, timeout, wait_for_n,
                                  visible)
    return _wait_for(driver, By.TAG_NAME, tag, timeout, visible, single)


def _wait_for(driver,
              locator_type,
              locator,
              timeout=10,
              visible=False,
              single=False):
    """Waits `timeout` seconds for the specified condition to be met. Condition is
    met if any matching element is found. Returns located element(s) when found.
    Args:
        driver: Selenium web driver instance
        locator_type: type of locator (e.g. By.CSS_SELECTOR or By.TAG_NAME)
        locator: name of tag, class, etc. to wait for
        timeout: how long to wait for presence/visibility of element
        visible: if True, require that element is not only present, but visible
        single: if True, return a single element, otherwise return a list of matching
        elements
    """
    wait = WebDriverWait(driver, timeout)
    if single:
        if visible:
            conditional = EC.visibility_of_element_located
        else:
            conditional = EC.presence_of_element_located
    else:
        if visible:
            conditional = EC.visibility_of_all_elements_located
        else:
            conditional = EC.presence_of_all_elements_located
    return wait.until(conditional((locator_type, locator)))


def _wait_for_multiple(driver,
                       locator_type,
                       locator,
                       timeout,
                       wait_for_n,
                       visible=False):
    """Waits until `wait_for_n` matching elements to be present (or visible).
    Returns located elements when found.
    Args:
        driver: Selenium web driver instance
        locator_type: type of locator (e.g. By.CSS_SELECTOR or By.TAG_NAME)
        locator: name of tag, class, etc. to wait for
        timeout: how long to wait for presence/visibility of element
        wait_for_n: wait until this number of matching elements are present/visible
        visible: if True, require that elements are not only present, but visible
    """
    wait = WebDriverWait(driver, timeout)

    def multiple_found(driver):
        elements = driver.find_elements(locator_type, locator)
        if visible:
            elements = [e for e in elements if e.is_displayed()]
        if len(elements) < wait_for_n:
            return False
        return elements

    return wait.until(multiple_found)


class CellTypeError(ValueError):

    def __init__(self, message=""):
        self.message = message


promise_js = """
var done = arguments[arguments.length - 1];
%s.then(
    data => { done(["success", data]); },
    error => { done(["error", error]); }
);
"""


def execute_promise(js, browser):
    state, data = browser.execute_async_script(promise_js % js)
    if state == 'success':
        return data
    raise Exception(data)


class Notebook:

    def __init__(self, browser):
        self.browser = browser
        self._disable_autosave_and_onbeforeunload()
        wait_for_selector(
            browser, "#panel", timeout=10, visible=False, single=True)
        self.prompt_cell = list(
            self.browser.find_elements_by_xpath(
                "//*[@id='panel-wrapper']/div"))[-1]

    def __len__(self):
        return len(self.cells)

    def __getitem__(self, key):
        return self.cells[key]

    def __setitem__(self, key, item):
        if isinstance(key, int):
            self.edit_cell(index=key, content=item, render=False)
        # TODO: re-add slicing support, handle general python slicing behaviour
        # includes: overwriting the entire self.cells object if you do
        # self[:] = []
        # elif isinstance(key, slice):
        #     indices = (self.index(cell) for cell in self[key])
        #     for k, v in zip(indices, item):
        #         self.edit_cell(index=k, content=v, render=False)

    def __iter__(self):
        return (cell for cell in self.cells)

    @property
    def body(self):
        return self.browser.find_element_by_tag_name("body")

    @property
    def cells(self):
        """Gets all cells once they are visible.
        """
        # For SOS note book, there are 2 extra cells, one is the selection box for kernel, the other is the preview panel
        return list(
            self.browser.find_elements_by_xpath(
                "//*[@id='notebook-container']/div"))

    @property
    def panel_cells(self):
        return list(self.browser.find_elements_by_xpath("//*[@id='panel']/div"))

    @property
    def current_index(self):
        return self.index(self.current_cell)

    def index(self, cell):
        return self.cells.index(cell)

    def save(self, name=''):
        if name:
            self.browser.execute_script(
                f"Jupyter.notebook.set_notebook_name(arguments[0])", name)
        time.sleep(5)
        return execute_promise('Jupyter.notebook.save_notebook()', self.browser)

    #
    # operation
    #

    def append_cell(self, *values, cell_type="code"):
        for i, value in enumerate(values):
            if isinstance(value, str):
                self.add_cell(cell_type=cell_type, content=value)
            else:
                raise TypeError("Don't know how to add cell from %r" % value)

    def add_cell(self, index=-1, cell_type="code", content=""):
        self._focus_cell(index)
        self.current_cell.send_keys("b")
        new_index = index + 1 if index >= 0 else index
        if content:
            self.edit_cell(index=new_index, content=content)
        if cell_type != 'code':
            self._convert_cell_type(index=new_index, cell_type=cell_type)

    def select_kernel(self, index=0, kernel_name="SoS", by_click=True):
        self._focus_cell(index)
        kernel_selector = "option[value='{}']".format(kernel_name)
        kernelList = self.current_cell.find_element_by_tag_name("select")
        kernel = wait_for_selector(kernelList, kernel_selector, single=True)
        if by_click:
            kernel.click()
        else:
            self.edit_cell(
                index=0, content="%use {}".format(kernel_name), render=True)

    def edit_cell(self, cell=None, index=0, content="", render=False):
        """Set the contents of a cell to *content*, by cell object or by index
        """
        if cell is not None:
            index = self.index(cell)

        # # Select & delete anything already in the cell
        # self.current_cell.send_keys(Keys.ENTER)

        # if platform == "darwin":
        #     command(self.browser, 'a')
        # else:
        #     ctrl(self.browser, 'a')

        # self.current_cell.send_keys(Keys.DELETE)
        self.browser.execute_script("IPython.notebook.get_cell(" + str(index) +
                                    ").set_text(" + repr(dedent(content)) + ")")
        self._focus_cell(index)

        if render:
            self.execute_cell(self.current_index)

    #
    # Get info
    #
    def get_kernel_list(self):
        kernelMenu = self.browser.find_element_by_id(
            "menu-change-kernel-submenu")
        kernelEntries = kernelMenu.find_elements_by_tag_name("a")
        kernels = []
        for kernelEntry in kernelEntries:
            kernels.append(kernelEntry.get_attribute('innerHTML'))
        return kernels

    def get_input_backgroundColor(self, index=0, in_console=False):
        if in_console:
            rgba = self.current_cell.find_element_by_class_name(
                "input_prompt").value_of_css_property("background-color")
        else:
            self._focus_cell(index)
            rgba = self.current_cell.find_element_by_class_name(
                "input_prompt").value_of_css_property("background-color")

        r, g, b, a = map(
            int,
            re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)', rgba).groups())
        return [r, g, b]

    def get_output_backgroundColor(self, index=0):

        rgba = self.current_cell.find_element_by_class_name(
            "out_prompt_overlay").value_of_css_property("background-color")
        r, g, b, a = map(
            int,
            re.search(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)', rgba).groups())
        return [r, g, b]

    #
    # Execution of cells
    #

    def execute_cell(self,
                     cell_or_index=None,
                     in_console=False,
                     expect_error=False):
        if isinstance(cell_or_index, int):
            index = cell_or_index
        elif isinstance(cell_or_index, WebElement):
            index = self.index(cell_or_index)
        else:
            raise TypeError("execute_cell only accepts a WebElement or an int")
        self._focus_cell(index)
        if in_console:
            self.current_cell.send_keys(Keys.CONTROL, Keys.SHIFT, Keys.ENTER)
            self._wait_for_done(-1, expect_error)
        else:
            self.current_cell.send_keys(Keys.CONTROL, Keys.ENTER)
            self._wait_for_done(index, expect_error)

    def call(self, content="", kernel="SoS", expect_error=False):
        '''
        Append a codecell to the end of the notebook, with specified `content` and
        `kernel`, execute it, waits for the completion of execution, and raise an
        exception if there is any error (stderr message), unless `expect_error` is
        set to `True`. This function returns the index of the cell, which can be
        used to retrieve output. Note that the `content` will be automatically
        dedented.
        '''
        # there will be at least a new cell from the new notebook.
        index = len(self.cells)
        self.add_cell(
            index=index - 1, cell_type="code", content=dedent(content))
        self.select_kernel(index=index, kernel_name=kernel, by_click=True)
        self.execute_cell(cell_or_index=index, expect_error=expect_error)
        return index

    def check_output(self,
                     content='',
                     kernel="SoS",
                     expect_error=False,
                     selector=None,
                     attribute='src'):
        '''
        This function calls call and gets its output with get_cell_output.
        '''
        return self.get_cell_output(
            self.call(content, kernel, expect_error),
            selector=selector,
            attribute=attribute)

    #
    # check output
    #

    def get_cell_output(self,
                        index=0,
                        in_console=False,
                        selector=None,
                        attribute='src'):
        outputs = ""
        if in_console:
            outputs = self.panel_cells[index].find_elements_by_css_selector(
                "div .output_subarea")
        else:
            outputs = self.cells[index].find_elements_by_css_selector(
                "div .output_subarea")
        output_text = ""
        has_error = False
        for output in outputs:
            if selector:
                try:
                    # some div might not have img
                    elem = output.find_element_by_css_selector(selector)
                    output_text += elem.get_attribute(attribute) + '\n'
                except NoSuchElementException:
                    pass
            #
            output_text += output.text + "\n"
        # if "Out" in output_text:
        #     output_text = "".join(output_text.split(":")[1:])

        return output_text.strip()

    #
    # For console panel
    #
    def is_console_panel_open(self):
        return bool(self.browser.find_element_by_id("panel").is_displayed())

    def toggle_console_panel(self):
        panelButton = self.browser.find_element_by_id("panel_button")
        panelButton.click()

    def edit_prompt_cell(self,
                         content,
                         kernel='SoS',
                         execute=False,
                         expect_error=False):
        # print("panel", self.prompt_cell.get_attribute("innerHTML"))
        self.browser.execute_script("window.my_panel.cell.set_text(" +
                                    repr(dedent(content)) + ")")

        # the div is not clickable so I use send_key to get around it
        self.prompt_cell.send_keys('\n')
        self.select_console_kernel(kernel)
        #   self.prompt_cell.find_element_by_css_selector('.CodeMirror').click()
        if execute:
            self.prompt_cell.send_keys(Keys.CONTROL, Keys.ENTER)
            self._wait_for_done(-1, expect_error=expect_error)

    def get_prompt_content(self):
        JS = 'return window.my_panel.cell.get_text();'
        return self.browser.execute_script(JS)

    def select_console_kernel(self, kernel_name="SoS"):
        kernel_selector = "option[value='{}']".format(kernel_name)
        kernelList = self.prompt_cell.find_element_by_tag_name("select")
        kernel = wait_for_selector(kernelList, kernel_selector, single=True)
        kernel.click()

    @classmethod
    def new_notebook(cls, browser, kernel_name='kernel-sos'):
        with new_window(browser, selector=".cell"):
            select_kernel(browser, kernel_name=kernel_name)
        return cls(browser)

    #
    # PRIVATE FUNCTIONS
    #

    def _disable_autosave_and_onbeforeunload(self):
        """Disable request to save before closing window and autosave.

        This is most easily done by using js directly.
        """
        self.browser.execute_script("window.onbeforeunload = null;")
        self.browser.execute_script("Jupyter.notebook.set_autosave_interval(0)")

    def _to_command_mode(self):
        """Changes us into command mode on currently focused cell

        """
        self.body.send_keys(Keys.ESCAPE)
        self.browser.execute_script(
            "return Jupyter.notebook.handle_command_mode("
            "Jupyter.notebook.get_cell("
            "Jupyter.notebook.get_edit_index()))")

    def _focus_cell(self, index=0):
        cell = self.cells[index]
        cell.click()
        self._to_command_mode()
        self.current_cell = cell

    def _convert_cell_type(self, index=0, cell_type="code"):
        # TODO add check to see if it is already present
        self._focus_cell(index)
        cell = self.cells[index]
        if cell_type == "markdown":
            self.current_cell.send_keys("m")
        elif cell_type == "raw":
            self.current_cell.send_keys("r")
        elif cell_type == "code":
            self.current_cell.send_keys("y")
        else:
            raise CellTypeError(
                ("{} is not a valid cell type,"
                 "use 'code', 'markdown', or 'raw'").format(cell_type))

        # self.wait_for_stale_cell(cell)
        self._focus_cell(index)
        return self.current_cell

    def _wait_for_done(self, index, expect_error=False):
        #
        # index < 0 means console panel
        while True:
            # main notebook
            if index >= 0:
                prompt = self.cells[index].find_element_by_css_selector(
                    '.input_prompt').text
            else:
                prompt = self.panel_cells[-1].find_element_by_css_selector(
                    '.input_prompt').text
            if '*' not in prompt:
                break
            else:
                time.sleep(0.1)
        # check if there is output
        try:
            # no output? OK.
            outputs = self.cells[index].find_elements_by_css_selector(
                "div .output_area")
        except NoSuchElementException:
            return
        #
        has_error = False
        for output in outputs:
            try:
                errors = output.find_element_by_css_selector('.output_stderr')
                if errors:
                    if expect_error:
                        has_error = True
                    else:
                        raise ValueError(
                            f'Cell produces error message: {errors.text}. Use expect_error=True to suppress this error if needed.'
                        )
            except NoSuchElementException:
                # if no error, ok
                pass
        #
        if expect_error and not has_error:
            raise ValueError(
                'Expect an error message from cell output, none found.')

    # def wait_for_output(self, index=0):
    #     time.sleep(10)
    #     return self.get_cell_output(index)

    # def set_cell_metadata(self, index, key, value):
    #     JS = 'Jupyter.notebook.get_cell({}).metadata.{} = {}'.format(
    #         index, key, value)
    #     return self.browser.execute_script(JS)

    # def get_cell_type(self, index=0):
    #     JS = 'return Jupyter.notebook.get_cell({}).cell_type'.format(index)
    #     return self.browser.execute_script(JS)

    # def set_cell_input_prompt(self, index, prmpt_val):
    #     JS = 'Jupyter.notebook.get_cell({}).set_input_prompt({})'.format(
    #         index, prmpt_val)
    #     self.browser.execute_script(JS)

    # def delete_cell(self, index):
    #     self._focus_cell(index)
    #     self._to_command_mode()
    #     self.current_cell.send_keys('dd')

    # def add_markdown_cell(self, index=-1, content="", render=True):
    #     self.add_cell(index, cell_type="markdown")
    #     self.edit_cell(index=index, content=content, render=render)

    # def extend(self, values):
    #     self.append_cell(*values)

    # def run_all(self):
    #     for cell in self:
    #         self.execute_cell(cell)

    # def trigger_keydown(self, keys):
    #     trigger_keystrokes(self.body, keys)

    # def add_and_execute_cell(self, index=-1, cell_type="code", content=""):
    #     self.add_cell(index=index, cell_type=cell_type, content=content)
    #     self.execute_cell(index)

    # def add_and_execute_cell_in_kernel(self, index=-1, cell_type="code", content="", kernel="SoS"):
    #     self.add_cell(index=index, cell_type=cell_type, content=content)
    #     self.select_kernel(index=index+1, kernel_name=kernel, by_click=True)
    #     self.execute_cell(cell_or_index=index+1)

    # def select_cell_range(self, initial_index=0, final_index=0):
    #     self._focus_cell(initial_index)
    #     self._to_command_mode()
    #     for i in range(final_index - initial_index):
    #         shift(self.browser, 'j')

    # def find_and_replace(self, index=0, find_txt='', replace_txt=''):
    #     self._focus_cell(index)
    #     self._to_command_mode()
    #     self.body.send_keys('f')
    #     wait_for_selector(self.browser, "#find-and-replace", single=True)
    #     self.browser.find_element_by_id("findreplace_allcells_btn").click()
    #     self.browser.find_element_by_id(
    #         "findreplace_find_inp").send_keys(find_txt)
    #     self.browser.find_element_by_id(
    #         "findreplace_replace_inp").send_keys(replace_txt)
    #     self.browser.find_element_by_id("findreplace_replaceall_btn").click()

    # def wait_for_stale_cell(self, cell):
    #     """ This is needed to switch a cell's mode and refocus it, or to render it.

    #     Warning: there is currently no way to do this when changing between
    #     markdown and raw cells.
    #     """
    #     wait = WebDriverWait(self.browser, 10)
    #     element = wait.until(EC.staleness_of(cell))

    # def get_cells_contents(self):
    #     JS = 'return Jupyter.notebook.get_cells().map(function(c) {return c.get_text();})'
    #     return self.browser.execute_script(JS)

    # def get_cell_contents(self, index=0, selector='div .CodeMirror-code'):
    #     return self.cells[index].find_element_by_css_selector(selector).text


def select_kernel(browser, kernel_name='kernel-sos'):
    """Clicks the "new" button and selects a kernel from the options.
    """
    wait = WebDriverWait(browser, 10)
    new_button = wait.until(
        EC.element_to_be_clickable((By.ID, "new-dropdown-button")))
    new_button.click()
    kernel_selector = '#{} a'.format(kernel_name)
    kernel = wait_for_selector(browser, kernel_selector, single=True)
    kernel.click()


@contextmanager
def new_window(browser, selector=None):
    """Contextmanager for switching to & waiting for a window created.

    This context manager gives you the ability to create a new window inside
    the created context and it will switch you to that new window.

    If you know a CSS selector that can be expected to appear on the window,
    then this utility can wait on that selector appearing on the page before
    releasing the context.

    Usage example:

        from notebook.tests.selenium.utils import new_window, Notebook

        ⋮ # something that creates a browser object

        with new_window(browser, selector=".cell"):
            select_kernel(browser, kernel_name=kernel_name)
        nb = Notebook(browser)

    """
    initial_window_handles = browser.window_handles
    yield
    new_window_handle = next(window for window in browser.window_handles
                             if window not in initial_window_handles)
    browser.switch_to.window(new_window_handle)
    if selector is not None:
        wait_for_selector(browser, selector)


def shift(browser, k):
    """Send key combination Shift+(k)"""
    trigger_keystrokes(browser, "shift-%s" % k)


def ctrl(browser, k):
    """Send key combination Ctrl+(k)"""
    trigger_keystrokes(browser, "control-%s" % k)


def command(browser, k):
    trigger_keystrokes(browser, "command-%s" % k)


def trigger_keystrokes(browser, *keys):
    """ Send the keys in sequence to the browser.
    Handles following key combinations
    1. with modifiers eg. 'control-alt-a', 'shift-c'
    2. just modifiers eg. 'alt', 'esc'
    3. non-modifiers eg. 'abc'
    Modifiers : http://seleniumhq.github.io/selenium/docs/api/py/webdriver/selenium.webdriver.common.keys.html
    """
    for each_key_combination in keys:
        keys = each_key_combination.split('-')
        if len(keys) > 1:  # key has modifiers eg. control, alt, shift
            modifiers_keys = [getattr(Keys, x.upper()) for x in keys[:-1]]
            ac = ActionChains(browser)
            for i in modifiers_keys:
                ac = ac.key_down(i)
            ac.send_keys(keys[-1])
            for i in modifiers_keys[::-1]:
                ac = ac.key_up(i)
            ac.perform()
        else:  # single key stroke. Check if modifier eg. "up"
            browser.send_keys(getattr(Keys, keys[0].upper(), keys[0]))


@pytest.mark.usefixtures("notebook")
class NotebookTest:
    pass
