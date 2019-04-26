#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.


from sos_notebook.test_utils import NotebookTest



class TestWorkflow(NotebookTest):

    def test_task(self, notebook):
        '''Test the execution of tasks with -s force'''
        idx = notebook.call('''\
            %set -v1
            %run -s force
            [10]
            input: for_each={'i': range(1)}
            task:
            python: expand=True
            import time
            print("this is {i}")
            time.sleep({i})

            [20]
            input: for_each={'i': range(2)}
            task:
            python: expand=True
            import time
            print("this aa is {i}")
            time.sleep({i})
            ''', kernel='SoS')

        output = notebook.get_cell_output(index=idx)
        assert "this aa is 1" in output and 'this is 0' in output

