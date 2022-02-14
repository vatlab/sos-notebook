#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import json
import os
import sys
import time
from subprocess import Popen
from urllib.parse import urljoin

import pytest
import requests
from selenium import webdriver
from selenium.webdriver import Chrome, Firefox, Remote
from testpath.tempdir import TemporaryDirectory
from webdriver_manager.chrome import ChromeDriverManager

from sos_notebook.test_utils import Notebook

pjoin = os.path.join


def _wait_for_server(proc, info_file_path):
    """Wait 30 seconds for the notebook server to start"""
    for i in range(300):
        if proc.poll() is not None:
            raise RuntimeError("Notebook server failed to start")
        if os.path.exists(info_file_path):
            try:
                with open(info_file_path) as f:
                    return json.load(f)
            except ValueError:
                # If the server is halfway through writing the file, we may
                # get invalid JSON; it should be ready next iteration.
                pass
        time.sleep(0.1)
    raise RuntimeError("Didn't find %s in 30 seconds", info_file_path)


@pytest.fixture(scope="session")
def notebook_server():
    info = {}
    temp_dir = TemporaryDirectory()
    td = temp_dir.name
    # do not use context manager because of https://github.com/vatlab/sos-notebook/issues/214
    if True:
        nbdir = info["nbdir"] = pjoin(td, "notebooks")
        os.makedirs(pjoin(nbdir, u"sub ∂ir1", u"sub ∂ir 1a"))
        os.makedirs(pjoin(nbdir, u"sub ∂ir2", u"sub ∂ir 1b"))
        # print(nbdir)
        info["extra_env"] = {
            "JUPYTER_CONFIG_DIR": pjoin(td, "jupyter_config"),
            "JUPYTER_RUNTIME_DIR": pjoin(td, "jupyter_runtime"),
            "IPYTHONDIR": pjoin(td, "ipython"),
        }
        env = os.environ.copy()
        env.update(info["extra_env"])

        command = [
            sys.executable,
            "-m",
            "notebook",
            "--no-browser",
            "--notebook-dir",
            nbdir,
            # run with a base URL that would be escaped,
            # to test that we don't double-escape URLs
            "--NotebookApp.base_url=/a@b/",
        ]
        print("command=", command)
        proc = info["popen"] = Popen(command, cwd=nbdir, env=env)
        info_file_path = pjoin(td, "jupyter_runtime", "nbserver-%i.json" % proc.pid)
        info.update(_wait_for_server(proc, info_file_path))

        print("Notebook server info:", info)
        yield info

    # manually try to clean up, which would fail under windows because
    # a permission error caused by iPython history.sqlite.
    try:
        temp_dir.cleanup()
    except:
        pass
    # Shut the server down
    requests.post(
        urljoin(info["url"], "api/shutdown"),
        headers={"Authorization": "token " + info["token"]},
    )


def make_sauce_driver():
    """This function helps travis create a driver on Sauce Labs.

    This function will err if used without specifying the variables expected
    in that context.
    """

    username = os.environ["SAUCE_USERNAME"]
    access_key = os.environ["SAUCE_ACCESS_KEY"]
    capabilities = {
        "tunnel-identifier": os.environ["TRAVIS_JOB_NUMBER"],
        "build": os.environ["TRAVIS_BUILD_NUMBER"],
        "tags": [os.environ["TRAVIS_PYTHON_VERSION"], "CI"],
        "platform": "Windows 10",
        "browserName": os.environ["JUPYTER_TEST_BROWSER"],
        "version": "latest",
    }
    if capabilities["browserName"] == "firefox":
        # Attempt to work around issue where browser loses authentication
        capabilities["version"] = "57.0"
    hub_url = "%s:%s@localhost:4445" % (username, access_key)
    print("Connecting remote driver on Sauce Labs")
    driver = Remote(
        desired_capabilities=capabilities, command_executor="http://%s/wd/hub" % hub_url
    )
    return driver


@pytest.fixture(scope="session")
def selenium_driver():

    if "JUPYTER_TEST_BROWSER" not in os.environ:
        os.environ["JUPYTER_TEST_BROWSER"] = "chrome"

    if os.environ.get("SAUCE_USERNAME"):
        driver = make_sauce_driver()
    elif os.environ.get("JUPYTER_TEST_BROWSER") == "live":
        driver = Chrome(ChromeDriverManager().install())
    elif os.environ.get("JUPYTER_TEST_BROWSER") == "chrome":
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1420,1080")
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        driver = Chrome(ChromeDriverManager().install(), options=chrome_options)
    elif os.environ.get("JUPYTER_TEST_BROWSER") == "firefox":
        driver = Firefox()
    else:
        raise ValueError(
            "Invalid setting for JUPYTER_TEST_BROWSER. Valid options include live, chrome, and firefox"
        )

    yield driver

    # Teardown
    driver.quit()


@pytest.fixture(scope="module")
def authenticated_browser(selenium_driver, notebook_server):
    selenium_driver.jupyter_server_info = notebook_server
    selenium_driver.get("{url}?token={token}".format(**notebook_server))
    return selenium_driver


@pytest.fixture(scope="class")
def notebook(authenticated_browser):
    return Notebook.new_notebook(authenticated_browser, kernel_name="kernel-sos")


@pytest.fixture()
def sample_scripts():
    if not os.path.isdir('temp'):
        os.mkdir('temp')
    with open('temp/script1.sos', 'w') as script:
        script.write('''
[0]
seq = range(3)
input: for_each='seq'
output: 'test${_seq}.txt'
print(output)
''')
    with open('temp/script2.sos', 'w') as script:
        # with tab after run:
        script.write('''
#! This is supposed to be a markdown
#! cell

[0]
seq = range(3)
input: for_each='seq'
output: 'test${_seq}.txt'
run:			concurrent=True
echo 'this is test script'
[10]
report('this is action report')
''')
    return ['temp/script1.sos', 'temp/script2.sos']


@pytest.fixture()
def sample_notebook():
    with open("sample_notebook.ipynb", "w") as sn:
        sn.write(r"""{
 "cells": [
  {
   "cell_type": "code",
   "execution_count": 1,
   "metadata": {
    "kernel": "SoS"
   },
   "outputs": [],
   "source": [
    "# this is a test workflow"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {
    "kernel": "SoS"
   },
   "source": [
    "This is a markdown cell"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 2,
   "metadata": {
    "kernel": "R"
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "This is a cell with another kernel"
     ]
    }
   ],
   "source": [
    "cat('This is a cell with another kernel')"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "metadata": {
    "kernel": "SoS"
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "This is a scratch cell\n"
     ]
    }
   ],
   "source": [
    "print('This is a scratch cell')"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {
    "kernel": "SoS"
   },
   "outputs": [],
   "source": [
    "# this comment will be included but not shown in help message\n",
    "# because it is for the global\n",
    "[global]\n",
    "a = 1\n",
    "# this comment will become the comment for parameter b\n",
    "parameter: b=2\n",
    "parameter: c=3 \n",
    "# this comment will become the comment for parameter d\n",
    "parameter: d='d'"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {
    "kernel": "SoS"
   },
   "outputs": [],
   "source": [
    "# this comment will not be included in exported workflow\n",
    "# because it is not immediately before section\n",
    "\n",
    "# this is a section comment, will be displayed\n",
    "[default]\n",
    "print(f'Hello {a}')"
   ]
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "SoS",
   "language": "sos",
   "name": "sos"
  },
  "language_info": {
   "codemirror_mode": "sos",
   "file_extension": ".sos",
   "mimetype": "text/x-sos",
   "name": "sos",
   "nbconvert_exporter": "sos_notebook.converter.SoS_Exporter",
   "pygments_lexer": "sos"
  },
  "sos": {
   "default_kernel": "SoS",
   "kernels": [
    [
     "R",
     "ir",
     "R",
     "#DCDCDA"
    ],
    [
     "SoS",
     "sos",
     "",
     ""
    ]
   ],
   "panel": {
    "displayed": true,
    "height": 0,
    "style": "side"
   },
   "version": "0.9.14.11"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}
""")
    return 'sample_notebook.ipynb'


@pytest.fixture()
def sample_papermill_notebook():
    with open("sample_mill_notebook.ipynb", "w") as sn:
        sn.write(r'''{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {
    "kernel": "SoS"
   },
   "source": [
    "## Notebook for testing papermill"
   ]
  },
  {
   "cell_type": "markdown",
   "metadata": {
    "kernel": "SoS"
   },
   "source": [
    "## Section 1"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 1,
   "metadata": {
    "kernel": "SoS",
    "tags": [
     "parameters"
    ]
   },
   "outputs": [],
   "source": [
    "# this is the parameter cell\n",
    "cutoff = 1"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 2,
   "metadata": {
    "kernel": "SoS"
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "1\n"
     ]
    }
   ],
   "source": [
    "# use of parameter cutoff\n",
    "print(cutoff)"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": 3,
   "metadata": {
    "kernel": "R"
   },
   "outputs": [
    {
     "name": "stdout",
     "output_type": "stream",
     "text": [
      "1"
     ]
    }
   ],
   "source": [
    "%expand\n",
    "cat(\"{cutoff}\")"
   ]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {
    "kernel": "R"
   },
   "outputs": [],
   "source": []
  }
 ],
 "metadata": {
  "kernelspec": {
   "display_name": "SoS",
   "language": "sos",
   "name": "sos"
  },
  "language_info": {
   "codemirror_mode": "sos",
   "file_extension": ".sos",
   "mimetype": "text/x-sos",
   "name": "sos",
   "nbconvert_exporter": "sos_notebook.converter.SoS_Exporter",
   "pygments_lexer": "sos"
  },
  "sos": {
   "celltoolbar": true,
   "kernels": [
    [
     "R",
     "ir",
     "R",
     "#FDEDEC",
     ""
    ],
    [
     "SoS",
     "sos",
     "",
     "",
     "sos"
    ]
   ],
   "panel": {
    "displayed": true,
    "height": 0,
    "style": "side"
   },
   "version": "0.21.15"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 4
}
''')
    return 'sample_mill_notebook.ipynb'