#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import time
from textwrap import dedent

def test_switch_kernel(notebook):
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
