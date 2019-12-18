#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.


from sos_notebook.test_utils import NotebookTest


class TestWorkflow(NotebookTest):

    def test_no_output(self, notebook):
        '''Test no output from workflow cell'''
        assert not notebook.check_output('''
            [1]
            print('hellp world')
            ''', kernel='SoS')

    def test_no_signature(self, notebook):
        '''Test no signature for interactive mode'''
        notebook.call('''
            output: 'a.txt'
            a=2
            _output.touch()
            ''', kernel='SoS')
        assert '2' in notebook.check_output('a', kernel='SoS')
        # change it
        assert '4' in notebook.check_output('''\
            a=4
            a''', kernel='SoS')
        # this step will be rerun again
        notebook.call('''
            output: 'a.txt'
            a=2
            _output.touch()
            ''', kernel='SoS')
        assert '2' in notebook.check_output('a', kernel='SoS')

    def test_task(self, notebook):
        '''Test the execution of tasks with -s force'''
        output = notebook.check_output('''\
            %run -s force -v1 -q localhost
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
        assert "Ran for < 5 seconds" in output
        assert 'this aa is' not in output
        assert 'start' not in output

    def test_identical_task(self, notebook):
        '''Test running two identical tasks in different cells #225'''
        output = notebook.check_output('''\
            %run -s force -q localhost
            task:
            print('hello')
            ''', kernel='SoS')
        assert "Ran for < 5 seconds" in output
        #
        output = notebook.check_output('''\
            %run -s force -q localhost
            task:
            print('hello')
            ''', kernel='SoS')
        assert "Ran for < 5 seconds" in output

    def test_background_mode(self, notebook):
        '''test executing sos workflows in background'''
        idx = notebook.call('''\
            %run &
            import time
            for i in range(5):
                print(f'output {i}')
                time.sleep(1)
            ''', kernel='SoS')
        output = notebook.get_cell_output(idx)
        assert 'output 4' not in output
        import time
        time.sleep(10)
        output = notebook.get_cell_output(idx)
        assert 'output 4' in output

    def test_warning_from_sos(self, notebook):
        '''Test warning message sent from sos'''
        notebook.call('''
            sh: allow_error=True
              eho something wrong
        ''')
