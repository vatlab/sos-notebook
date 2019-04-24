
#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import time
from textwrap import dedent
from sos.utils import env
import pytest
import os
import sys


@pytest.mark.usefixtures("notebook")
class BasicTest:
    pass


class TestMagics(BasicTest):

    def test_magic_in_subkernel(self, notebook):
        '''test %pwd in the python3 kernel (which is not a sos magic)'''
        idx = notebook.append_and_execute_cell_in_kernel(
            content="%pwd", kernel="Python3")
        assert len(notebook.get_cell_output(index=idx)) > 0

    def test_help_messages(self, notebook):
        '''test help functions of magics'''
        for magic in ('cd',
                      'debug', 'dict', 'get', 'matplotlib', 'preview',
                      'put', 'render', 'run', 'runfile', 'save', 'sandbox',
                      'sessioninfo', 'set', 'sosrun', 'sossave', 'shutdown',
                      'task', 'toc', 'use', 'with'):
            idx = notebook.append_and_execute_cell_in_kernel(
                content=f"%{magic} -h", kernel="SoS")
            # output does not have error
            assert magic in notebook.get_cell_output(index=idx)

    def test_magic_capture(self, notebook):
        # test %capture
        idx = notebook.append_and_execute_cell_in_kernel(dedent("""\
            %capture --to R_out
            cat('this is to stdout')
            """), kernel="R")
        assert 'this is to stdout' == notebook.get_cell_output(index=idx)

        idx = notebook.append_and_execute_cell_in_kernel(
            content="%capture --to R_out \n ", kernel="R")
        idx = notebook.append_and_execute_cell_in_kernel(
            content="R_out", kernel="SoS")
        assert "''" == notebook.get_cell_output(index=idx)
        #
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %capture text --to R_out
            paste('this is the return value')
            """), kernel="R")
        idx = notebook.append_and_execute_cell_in_kernel(
            content="R_out", kernel="SoS")
        assert "this is the return value" in notebook.get_cell_output(
            index=idx)
        # capture as csv
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %capture --as csv --to res
            print('a,b\\nc,d')
            """), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            res
            """), kernel="SoS")
        assert "a" in notebook.get_cell_output(index=idx)
        # capture as tsv
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %capture --as tsv --to res
            print('a\\tb\\nc\\td')
            """), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            res
            """), kernel="SoS")
        assert "a" in notebook.get_cell_output(index=idx)
        # capture as json
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %capture --as json --to res
            print('[1,2,3]')
            """), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            res
            """), kernel="SoS")
        assert "[1, 2, 3]" in notebook.get_cell_output(index=idx)

    def test_magic_cd(self, notebook):
        # magic cd that changes directory of all subfolders
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            import os
            print(os.getcwd())
            '''), kernel="Python3")
        output1 = notebook.get_cell_output(index=idx)
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %cd ..
            '''), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            import os
            print(os.getcwd())
            '''), kernel="Python3")
        output2 = notebook.get_cell_output(index=idx)
        #
        assert len(output1) > len(output2)
        assert output1.startswith(output2)

    def test_magic_clear(self, notebook):
        # test %clear
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %clear --all
            '''), kernel="SoS")
        # check output

    def test_magic_connectinfo(self, notebook):
        # test %capture
        idx = notebook.append_and_execute_cell_in_kernel(dedent("""\
            %connectinfo
            """), kernel="SoS")
        assert 'Connection file' in notebook.get_cell_output(index=idx)

    def test_magic_debug(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %debug on
            %debug off
            """), kernel="SoS")

    def test_magic_dict(self, notebook):
        # test %dict
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            R_out = 1
            ran = 5
            '''), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %dict --keys
            '''), kernel="SoS")
        keylist = notebook.get_cell_output(index=idx)
        assert 'R_out' in keylist and 'ran' in keylist
        #
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %dict ran
            '''), kernel="SoS")
        assert 'r' in notebook.get_cell_output(index=idx)
        #
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %dict --reset
            %dict --keys
            '''), kernel="SoS")
        assert 'R_out' not in notebook.get_cell_output(index=idx)

    def test_magic_expand(self, notebook):
        # test %expand
        idx = notebook.append_and_execute_cell_in_kernel(
            content="par=100", kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %expand ${ }
            if (${par} > 50) {
                cat('A parameter ${par} greater than 50 is specified.');
            }
            """), kernel="R")
        assert "A parameter 100 greater than 50 is specified." == notebook.get_cell_output(
            index=idx)

    def test_magic_get(self, notebook):
        # test %get
        command = "a = [1, 2, 3] \nb = [1, 2, '3']"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="SoS")
        command = "%get a \na"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="Python3")
        assert "[1, 2, 3]" == notebook.get_cell_output(index=idx)
        command = "%get b \nstr(b)\nR_var <- 'R variable'"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="R")
        assert "List of 3" in notebook.get_cell_output(index=idx)
        command = "%get --from R R_var \n R_var"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="Python3")
        assert "R variable" in notebook.get_cell_output(index=idx)

    def test_magic_matplotlib(self, notebook):
        # test %capture
        idx = notebook.append_and_execute_cell_in_kernel(dedent("""\
            %matplotlib inline

            import matplotlib.pyplot as plt
            import numpy as np
            x = np.linspace(0, 10)
            plt.plot(x, np.sin(x), '--', linewidth=2)
            plt.show()
            """), kernel="SoS")
        assert 'data:image/png;base64' in notebook.get_elems_in_cell_output(
            index=idx, selector='img')

    def test_magic_render(self, notebook):
        # test %put from subkernel to SoS Kernel
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %render
            """
            # header

            * item1
            * item2
            """
            '''), kernel="SoS")
        assert "header" in notebook.get_cell_output(index=idx)

    def test_magic_run(self, notebook):
        # test passing parameters and %run
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %run --floatvar 1 --test_mode --INT_LIST 1 2 3 --infile a.txt
            VAR = 'This var is defined without global.'
            [global]
            GLOBAL_VAR='This var is defined with global.'
            [step_1]
            CELL_VAR='This var is defined in Cell.'
            parameter: floatvar=float
            parameter: stringvar='stringvar'
            print(VAR)
            print(GLOBAL_VAR)
            print(CELL_VAR)
            print(floatvar)
            print(stringvar)
            [step_2]
            parameter: test_mode=bool
            parameter: INT_LIST=[]
            parameter: infile = path
            parameter: b=1
            print(test_mode)
            print(INT_LIST)
            print(infile.name)
            sh: expand=True
            echo {b}
            '''), kernel='SoS')
        output = notebook.get_cell_output(index=idx)
        lines = output.splitlines()
        results = ["This var is defined without global.", "This var is defined with global.", "This var is defined in Cell.", "1.0", "stringvar",
                   "True", "['1', '2', '3']", "a.txt", "1"]
        for index, line in enumerate(lines):
            assert lines[index] == results[index]

    def test_magic_runfile(self, notebook):
        #
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %save check_run -f
            %run --var 1
            parameter: var=0
            sh: expand=True
            echo {var}
            '''), kernel='SoS')
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %runfile check_run --var=2
        '''), kernel='SoS')
        output = notebook.get_cell_output(index=idx)
        assert output == "2"

    @pytest.mark.skipif(sys.platform == 'win32' or 'TRAVIS' in os.environ, reason="Skip test because of no internet connection or in travis test")
    def test_magic_preview_dot(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a.dot
            with open('a.dot', 'w') as dot:
                dot.write("""\
            graph graphname {
                a -- b -- c;
                b -- d;
            }
            """)
            '''), kernel="SoS")
        assert 'a.dot' in notebook.get_cell_output(index=idx)
        assert 'data:image/png;base64' in notebook.get_elems_in_cell_output(
            index=idx, selector='img')

    def test_magic_preview_var(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a
            a=1
            '''), kernel="SoS")
        assert '> a: int' in notebook.get_cell_output(index=idx)

    def test_magic_preview_csv(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a.csv
            with open('a.csv', 'w') as csv:
                csv.write("""\
                a,b,c
                1,2,3
                4,5,6
                """)
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.csv' in output
        assert ' a   b   c ' in output

    def test_magic_preview_txt(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a.txt
            with open('a.txt', 'w') as txt:
                txt.write("""\
            hello
            world
            """)
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.txt' in output
        assert '2 lines' in output

    def test_magic_preview_zip(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            !echo "blah" > a.csv
            %preview -n a.zip
            import zipfile

            with zipfile.ZipFile('a.zip', 'w') as zfile:
                zfile.write('a.csv')
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.zip' in output
        assert '1 file' in output
        assert 'a.csv' in output

    def test_magic_preview_tar(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            !echo "blah" > a.csv
            %preview -n a.tar
            import tarfile

            with tarfile.open('a.tar', 'w') as tar:
                tar.add('a.csv')
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.tar' in output
        assert '1 file' in output
        assert 'a.csv' in output

    def test_magic_preview_tar_gz(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            !echo "blah" > a.csv
            %preview -n a.tar.gz
            import tarfile

            with tarfile.open('a.tar.gz', 'w:gz') as tar:
                tar.add('a.csv')
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.tar.gz' in output
        assert '1 file' in output
        assert 'a.csv' in output

    def test_magic_preview_gz(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a.gz
            import gzip

            with gzip.open('a.gz', 'w') as gz:
                gz.write(b"""
            Hello
            world
            """)
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.gz' in output
        assert 'Hello' in output
        assert 'world' in output

    def test_magic_preview_md(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %preview -n a.md
            with open('a.md', 'w') as md:
                md.write("""\
            # title

            * item1
            * item2
            """)
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.md' in output
        assert 'title' in output
        assert 'item2' in output

    def test_magic_preview_html(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent('''\
%preview -n a.html
with open('a.html', 'w') as dot:
    dot.write("""\
<!DOCTYPE html>
<html>
<body>

<h1>My First Heading</h1>

<p>My first paragraph.</p>

</body>
</html>
""")
            '''), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert '> a.html' in output
        assert 'My First Heading' in output
        assert 'My first paragraph' in output

    def test_magic_put(self, notebook):
        # test %put from subkernel to SoS Kernel
        notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %put a b c R_var
            a <- c(1)
            b <- c(1, 2, 3)
            c <- matrix(c(1,2,3,4), ncol=2)
            R_var <- 'R variable'
            '''), kernel="R")
        idx = notebook.append_and_execute_cell_in_kernel(
            content='a', kernel="SoS")
        assert "1" in notebook.get_cell_output(index=idx)
        idx = notebook.append_and_execute_cell_in_kernel(
            content='b', kernel="SoS")
        assert "[1, 2, 3]" in notebook.get_cell_output(index=idx)
        idx = notebook.append_and_execute_cell_in_kernel(
            content='c', kernel="SoS")
        assert "array" in notebook.get_cell_output(index=idx)
        idx = notebook.append_and_execute_cell_in_kernel(
            content='R_var', kernel="SoS")
        assert "R variable" in notebook.get_cell_output(index=idx)
        # test %put from SoS to other kernel
        #
        notebook.append_and_execute_cell_in_kernel(content=dedent('''\
            %put a1 b1 --to R
            a1 = 123
            b1 = 'this is python'
            '''), kernel="SoS")
        idx = notebook.append_and_execute_cell_in_kernel(
            content='cat(a1)', kernel="R")
        assert "123" in notebook.get_cell_output(index=idx)
        idx = notebook.append_and_execute_cell_in_kernel(
            content='cat(b1)', kernel="R")
        assert "this is python" in notebook.get_cell_output(index=idx)

    def test_magic_sandbox(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %sandbox
            with open('test_blah.txt', 'w') as tb:
                tb.write('a')
            """), kernel="SoS")
        assert not os.path.isfile('test_blah.txt')

    def test_magic_save(self, notebook):
        tmp_file = os.path.join(os.path.expanduser('~'), 'test_save.txt')
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %save ~/test_save.txt
            a=1
            """), kernel="SoS")
        with open(tmp_file) as tt:
            assert tt.read() == 'a=1\n'
        os.remove(tmp_file)

    def test_magic_sessioninfo(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %use Python3
            %use SoS
            %sessioninfo
            """), kernel="SoS")
        output = notebook.get_cell_output(index=idx)
        assert 'SoS Version' in output
        assert 'Python3' in output

    def test_magic_set(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %set
            %set -v2
            %set
            %set -v1
            """), kernel="SoS")
        assert "set" in notebook.get_cell_output(index=idx)

    @pytest.mark.skipIf(sys.platform == 'win32', reason='! magic does not support built-in command #203')
    def test_magic_shell(self, notebook):
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            !echo haha
            """), kernel="SoS")
        assert "haha" in notebook.get_cell_output(index=idx)

    def test_magic_sossave(self, notebook):
        tmp_file = os.path.join(os.path.expanduser('~'), 'test_sossave.html')
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        idx = notebook.append_and_execute_cell_in_kernel(content=dedent("""\
            %sossave ~/test_sossave.html --force
            [10]
            print('kkk')
            """), kernel="SoS")
        with open(tmp_file) as tt:
            assert 'kkk' in tt.read()
        os.remove(tmp_file)

    def test_sos_vars(self, notebook):
        # test automatic tranfer of sos variables
        command = str("sosa = f'{3*8}'")
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="Python3")
        command = "sosa"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="SoS")
        assert "24" in notebook.get_cell_output(index=idx)

    def test_magic_with(self, notebook):
        # test %with
        command = "a = 3"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="SoS")
        command = "%with R -i a -o ran \nran<-rnorm(a)"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="SoS")
        command = "ran"
        idx = notebook.append_and_execute_cell_in_kernel(
            content=command, kernel="SoS")
        assert len(notebook.get_cell_output(index=idx)) > 0
