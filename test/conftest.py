#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import tempfile

import pytest

from sos_notebook.test_utils import Notebook


@pytest.fixture(scope="class")
def notebook():
    """Provide a notebook interface for kernel testing"""
    return Notebook()


@pytest.fixture()
def sample_scripts():
    if not os.path.isdir("temp"):
        os.mkdir("temp")
    with open("temp/script1.sos", "w") as script:
        script.write("""
[0]
seq = range(3)
input: for_each='seq'
output: 'test${_seq}.txt'
print(output)
""")
    with open("temp/script2.sos", "w") as script:
        # with tab after run:
        script.write("""
#! This is supposed to be a markdown
#! cell

[0]
seq = range(3)
input: for_each='seq'
output: 'test${_seq}.txt'
run:\t\t\tconcurrent=True
echo 'this is test script'
[10]
report('this is action report')
""")
    return ["temp/script1.sos", "temp/script2.sos"]


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
    return "sample_notebook.ipynb"


@pytest.fixture()
def sample_papermill_notebook():
    with open("sample_mill_notebook.ipynb", "w") as sn:
        sn.write(r"""{
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
""")
    return "sample_mill_notebook.ipynb"
