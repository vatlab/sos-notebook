#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import pytest
import os
import sys
import tempfile

from sos_notebook.test_utils import NotebookTest


class TestMagics(NotebookTest):

    def test_magic_in_subkernel(self, notebook):
        """test %pwd in the python3 kernel (which is not a sos magic)"""
        assert len(notebook.check_output("%pwd", kernel="Python3")) > 0

    def test_help_messages(self, notebook):
        """test help functions of magics"""
        for magic in (
                "cd",
                "debug",
                "dict",
                "get",
                "matplotlib",
                "preview",
                "put",
                "render",
                'revisions',
                "run",
                "runfile",
                "save",
                "sandbox",
                "sessioninfo",
                "set",
                "sosrun",
                "sossave",
                "shutdown",
                "task",
                "toc",
                "use",
                "with",
        ):
            output = notebook.check_output(f"%{magic} -h", kernel="SoS")
            # output does not have error
            assert magic in output

    def test_magic_capture(self, notebook):
        # test %capture
        # capture raw (default)
        notebook.call(
            """\
            %capture
            cat('this is to stdout')
            """,
            kernel="R",
        )
        output = notebook.check_output('__captured', kernel='SoS')
        assert 'stream' in output and 'stdout' in output and 'this is to stdout' in output
        # specify raw
        notebook.call(
            """\
            %capture raw
            cat('this is to stdout')
            """,
            kernel="R",
        )
        output = notebook.check_output('__captured', kernel='SoS')
        assert 'stream' in output and 'stdout' in output and 'this is to stdout' in output
        #
        # capture SoS execute_result (#220)
        notebook.call(
            """\
            %capture raw
            'this is to texts'
            """,
            kernel="SoS",
        )
        output = notebook.check_output('__captured', kernel='SoS')
        assert 'execute_result' in output and 'text/plain' in output and 'this is to texts' in output
        #
        # capture to variable
        assert (notebook.check_output(
            """\
            %capture stdout --to R_out
            cat('this is to stdout')
            """,
            kernel="R",
        ) == "this is to stdout")
        #
        notebook.call("%capture stdout --to R_out \n ", kernel="R")
        assert notebook.check_output("R_out", kernel="SoS") == "''"
        #
        notebook.call(
            """\
            %capture text --to R_out
            paste('this is the return value')
            """,
            kernel="R",
        )
        output = notebook.check_output("R_out", kernel="SoS")
        assert "this is the return value" in output
        #
        # capture as csv
        notebook.call(
            """\
            %capture stdout --as csv --to res
            print('a,b\\nc,d')
            """,
            kernel="SoS",
        )
        assert "a" in notebook.check_output("res", kernel="SoS")
        assert "DataFrame" in notebook.check_output("type(res)", kernel="SoS")
        #
        # capture as tsv
        notebook.call(
            """\
            %capture stdout --as tsv --to res
            print('a\\tb\\nc\\td')
            """,
            kernel="SoS",
        )
        assert "a" in notebook.check_output("res", kernel="SoS")
        assert "DataFrame" in notebook.check_output("type(res)", kernel="SoS")
        #
        # capture as json
        notebook.call(
            """\
            %capture stdout --as json --to res
            print('[1,2,3]')
            """,
            kernel="SoS",
        )
        assert "[1, 2, 3]" in notebook.check_output('res', kernel="SoS")
        #
        # test append to str
        notebook.call(
            """\
            %capture stdout --to captured_text
            print('from sos')
            """,
            kernel="SoS",
        )
        notebook.call(
            """\
            %capture stdout --append captured_text
            cat('from R')
            """,
            kernel="R",
        )
        output = notebook.check_output("captured_text", kernel="SoS")
        assert 'from sos' in output and 'from R' in output
        assert 'str' in notebook.check_output(
            "type(captured_text)", kernel="SoS")
        # test append to dataframe
        notebook.call(
            """\
            %capture stdout --as tsv --to table
            print('a\\tb\\n11\\t22')
            """,
            kernel="SoS",
        )
        notebook.call(
            """\
            %capture stdout --as tsv --append table
            print('a\\tb\\n33\\t44')
            """,
            kernel="SoS",
        )
        output = notebook.check_output("table", kernel="SoS")
        assert '11' in output and '22' in output and '33' in output and '44' in output
        assert 'DataFrame' in notebook.check_output("type(table)", kernel="SoS")

    def test_magic_cd(self, notebook):
        # magic cd that changes directory of all subfolders
        output1 = notebook.check_output(
            """\
            import os
            print(os.getcwd())
            """,
            kernel="Python3",
        )
        notebook.call("%cd ..", kernel="SoS")
        output2 = notebook.check_output(
            """\
            import os
            print(os.getcwd())
            """,
            kernel="Python3",
        )
        assert len(output1) > len(output2) and output1.startswith(output2)

    def test_magic_clear(self, notebook):
        # test %clear
        notebook.call("%clear --all", kernel="SoS")

    def test_magic_connectinfo(self, notebook):
        # test %capture
        assert "Connection file" in notebook.check_output(
            "%connectinfo", kernel="SoS")

    def test_magic_debug(self, notebook):
        assert "debug" in notebook.check_output(
            """\
            %debug on
            %debug off
            """,
            kernel="SoS",
            expect_error=True,
        )

    def test_magic_dict(self, notebook):
        # test %dict
        notebook.call(
            """\
            R_out = 1
            ran = 5
            """,
            kernel="SoS",
        )
        output = notebook.check_output(
            """\
            %dict --keys
            """,
            kernel="SoS",
        )
        assert "R_out" in output and "ran" in output
        #
        assert "r" in notebook.check_output("%dict ran", kernel="SoS")
        #
        assert "R_out" not in notebook.check_output(
            """\
            %dict --reset
            %dict --keys
            """,
            kernel="SoS",
        )

    def test_magic_expand(self, notebook):
        # test %expand
        notebook.call("par=100", kernel="SoS")
        assert "A parameter {par} greater than 50 is specified." == notebook.check_output(
            """\
            cat('A parameter {par} greater than 50 is specified.');
            """,
            kernel="R",
        )
        assert "A parameter 100 greater than 50 is specified." == notebook.check_output(
            """\
            %expand
            if ({par} > 50) {{
                cat('A parameter {par} greater than 50 is specified.');
            }}
            """,
            kernel="R",
        )
        assert "A parameter 100 greater than 50 is specified." == notebook.check_output(
            """\
            %expand ${ }
            if (${par} > 50) {
                cat('A parameter ${par} greater than 50 is specified.');
            }
            """,
            kernel="R",
        )
        assert "A parameter 100 greater than 50 is specified." == notebook.check_output(
            """\
            %expand [ ]
            if ([par] > 50) {
                cat('A parameter [par] greater than 50 is specified.');
            }
            """,
            kernel="R",
        )

    def test_magic_get(self, notebook):
        # test %get
        notebook.call(
            """\
            a = [1, 2, 3]
            b = [1, 2, '3']
            """,
            kernel="SoS",
        )
        assert "[1, 2, 3]" == notebook.check_output(
            """\
            %get a
            a
            """,
            kernel="Python3",
        )
        assert "List of 3" in notebook.check_output(
            """\
            %get b
            str(b)
            R_var <- 'R variable'
            """,
            kernel="R",
        )
        assert "R variable" in notebook.check_output(
            """\
            %get --from R R_var
            R_var
            """,
            kernel="Python3",
        )
        #
        # get with different variable names
        notebook.call(
            """\
            a = 1025
            _b_a = 22
            """,
            kernel="SoS",
        )
        assert "1025" == notebook.check_output(
            """\
            %get a
            b <- 122
            c <- 555
            a
            """,
            kernel="R",
        )
        #
        assert "22" in notebook.check_output(
            """\
            %get _b_a
            .b_a
            """,
            kernel="R",
            expect_error=True,
        )
        #
        # get from another kernel
        assert "555" in notebook.check_output(
            """\
            %get c --from R
            c
            """,
            kernel="R",
        )

    def test_magic_matplotlib(self, notebook):
        # test %capture
        pytest.importorskip("matplotlib")
        assert "data:image/png;base64" in notebook.check_output(
            """\
            %matplotlib inline

            import matplotlib.pyplot as plt
            import numpy as np
            x = np.linspace(0, 10)
            plt.plot(x, np.sin(x), '--', linewidth=2)
            plt.show()
            """,
            kernel="SoS",
            selector="img",
            attribute="src",
        )

    def test_magic_render(self, notebook):
        # test %put from subkernel to SoS Kernel
        output = notebook.check_output(
            '''\
            %render
            """
            # header

            * item1
            * item2
            """
            ''',
            kernel="SoS",
        )
        assert "header" in output and 'item1' in output and 'item2' in output
        assert '# header' not in output and '* item1' not in output and '* item2' not in output
        # render wrong type from subkernel
        output = notebook.check_output(
            '''\
            %render text
            cat("\\n# header\\n* item1\\n* item2\\n")
            ''',
            kernel="R",
        )
        assert "header" not in output and 'item1' not in output and 'item2' not in output
        # render correct type
        output = notebook.check_output(
            '''\
            %render
            cat("\\n# header\\n* item1\\n* item2\\n")
            ''',
            kernel="R",
        )
        assert "header" in output and 'item1' in output and 'item2' in output
        #
        # test render as other types
        output = notebook.check_output(
            '''\
            %render --as Latex
            """
            $$c = \\sqrt{a^2 + b^2}$$
            """
            ''',
            kernel="SoS")
        assert "c=" in output and 'a2+b2' in output

    def test_magic_run(self, notebook):
        # test passing parameters and %run
        output = notebook.check_output(
            """\
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
            python: expand=True
            print({b})
            """,
            kernel="SoS",
        )
        lines = output.splitlines()
        results = [
            "This var is defined without global.",
            "This var is defined with global.",
            "This var is defined in Cell.",
            "1.0",
            "stringvar",
            "True",
            "['1', '2', '3']",
            "a.txt",
            "1",
        ]
        for index, line in enumerate(lines):
            assert lines[index] == results[index]

    def test_magic_runfile(self, notebook):
        #
        notebook.call(
            """\
            %save check_run -f
            %run --var 1
            parameter: var=0
            python: expand=True
            print({var})
            """,
            kernel="SoS",
        )
        assert "2" == notebook.check_output(
            "%runfile check_run --var=2", kernel="SoS")

    @pytest.mark.skipif(
        sys.platform == "win32" or "TRAVIS" in os.environ,
        reason="Skip test because of no internet connection or in travis test",
    )
    def test_magic_preview_dot(self, notebook):
        output = notebook.check_output(
            '''
            %preview -n a.dot
            with open('a.dot', 'w') as dot:
                dot.write("""\\
            graph graphname {
                a -- b -- c;
                b -- d;
            }
            """)
            ''',
            kernel="SoS",
            selector="img",
        )
        assert "a.dot" in output and "data:image/png;base64" in output

    def test_magic_preview_in_R(self, notebook):
        assert "mtcars" in notebook.check_output(
            """\
            %preview -n mtcars
            %use R
            """,
            kernel="R",
        )

    def test_magic_preview_png(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.png
            R:
                png('a.png')
                plot(0)
                dev.off()
            """,
            kernel="SoS",
            selector="img",
        )
        assert "a.png" in output and "data:image/png;base64" in output

    def test_magic_preview_jpg(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.jp*
            R:
                jpeg('a.jpg')
                plot(0)
                dev.off()
            """,
            kernel="SoS",
            selector="img",
        )
        assert "a.jpg" in output and ("data:image/jpeg;base64" in output or
                                      "data:image/png;base64" in output)

    def test_magic_preview_pdf(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.pdf
            R:
                pdf('a.pdf')
                plot(0)
                dev.off()
            """,
            kernel="SoS",
            selector="embed",
            attribute="type",
        )
        assert "a.pdf" in output and (
            "application/x-google-chrome-pdf" in output or
            "application/pdf" in output)

    @pytest.mark.xfail(
        reason='Some system has imagemagick refusing to read PDF due to policy reasons.'
    )
    def test_magic_preview_pdf_as_png(self, notebook):
        try:
            from wand.image import Image
        except ImportError:
            pytest.skip("Skip because imagemagick is not properly installed")
        # preview as png
        output = notebook.check_output(
            """\
            %preview -n a.pdf -s png
            R:
                pdf('a.pdf')
                plot(0)
                dev.off()
            """,
            kernel="SoS",
            selector="img",
        )
        assert "a.pdf" in output and "data:image/png;base64" in output

    def test_magic_preview_var(self, notebook):
        assert "> a: int" in notebook.check_output(
            """\
            %preview -n a
            a=1
            """,
            kernel="SoS",
        )

    def test_magic_preview_var_limit(self, notebook):
        output = notebook.check_output(
            """\
            %preview var -n -l 5
            import numpy as np
            import pandas as pd
            var = pd.DataFrame(
                np.asmatrix([[i*10, i*10+1] for i in range(100)]))
            """,
            kernel="SoS",
        )
        assert "var" in output and "41" in output and "80" not in output

    # def test_magic_preview_var_scatterplot(self, notebook):
    #     output = notebook.check_output('''\
    #         %preview mtcars -n -s scatterplot mpg disp --by cyl
    #         %get mtcars --from R
    #         ''', kernel="SoS")

    # def test_magic_preview_var_scatterplot_tooltip(self, notebook):
    #     output = notebook.check_output('''\
    #         %preview mtcars -n -s scatterplot _index disp hp mpg --tooltip wt qsec
    #         %get mtcars --from R
    #         ''', kernel="SoS")

    # def test_magic_preview_var_scatterplot_log(self, notebook):
    #     output = notebook.check_output('''\
    #         %preview mtcars -n -s scatterplot disp hp --log xy --xlim 60 80 --ylim 40 300
    #         %get mtcars --from R
    #         ''', kernel="SoS")

    def test_magic_preview_csv(self, notebook):
        output = notebook.check_output(
            '''\
            %preview -n a.csv
            with open('a.csv', 'w') as csv:
                csv.write("""\
                a,b,c
                1,2,3
                4,5,6
                """)
            ''',
            kernel="SoS",
        )
        assert "> a.csv" in output and " a   b   c " in output

    def test_magic_preview_txt(self, notebook):
        output = notebook.check_output(
            '''\
            %preview -n a.txt
            with open('a.txt', 'w') as txt:
                txt.write("""\
            hello
            world
            """)
            ''',
            kernel="SoS",
        )
        assert "> a.txt" in output and "2 lines" in output

    def test_magic_preview_zip(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.zip
            import zipfile
            with open('a.csv', 'w') as tmp:
                tmp.write('blah')
            with zipfile.ZipFile('a.zip', 'w') as zfile:
                zfile.write('a.csv')
            """,
            kernel="SoS",
        )
        import time
        time.sleep(20)
        assert "> a.zip" in output and "1 file" in output and "a.csv" in output

    def test_magic_preview_tar(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.tar
            import tarfile
            with open('a.csv', 'w') as tmp:
                tmp.write('blah')
            with tarfile.open('a.tar', 'w') as tar:
                tar.add('a.csv')
            """,
            kernel="SoS",
        )
        assert "> a.tar" in output and "1 file" in output and "a.csv" in output

    def test_magic_preview_tar_gz(self, notebook):
        output = notebook.check_output(
            """\
            %preview -n a.tar.gz
            import tarfile
            with open('a.csv', 'w') as tmp:
                tmp.write('blah')
            with tarfile.open('a.tar.gz', 'w:gz') as tar:
                tar.add('a.csv')
            """,
            kernel="SoS",
        )
        assert "> a.tar.gz" in output and "1 file" in output and "a.csv" in output

    def test_magic_preview_gz(self, notebook):
        output = notebook.check_output(
            '''\
            %preview -n a.gz
            import gzip

            with gzip.open('a.gz', 'w') as gz:
                gz.write(b"""
            Hello
            world
            """)
            ''',
            kernel="SoS",
        )
        assert "> a.gz" in output and "Hello" in output and "world" in output

    def test_magic_preview_md(self, notebook):
        output = notebook.check_output(
            '''\
            %preview -n a.md
            with open('a.md', 'w') as md:
                md.write("""\
            # title

            * item1
            * item2
            """)
            ''',
            kernel="SoS",
        )
        assert "> a.md" in output and "title" in output and "item2" in output

    def test_magic_preview_html(self, notebook):
        output = notebook.check_output(
            '''\
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
            ''',
            kernel="SoS",
        )
        assert ("> a.html" in output and "My First Heading" in output and
                "My first paragraph" in output)

    def test_magic_put(self, notebook):
        # test %put from subkernel to SoS Kernel
        notebook.call(
            """\
            %put a b c R_var
            a <- c(1)
            b <- c(1, 2, 3)
            R_var <- 'R variable'
            """,
            kernel="R",
        )

        assert "1" in notebook.check_output(content="a", kernel="SoS")

        assert "[1, 2, 3]" in notebook.check_output(content="b", kernel="SoS")

        assert "R variable" in notebook.check_output(
            content="R_var", kernel="SoS")

        # test %put from SoS to other kernel
        #
        notebook.call(
            """\
            %put a1 b1 --to R
            a1 = 123
            b1 = 'this is python'
            """,
            kernel="SoS",
        )
        assert "123" in notebook.check_output(content="cat(a1)", kernel="R")

        assert "this is python" in notebook.check_output(
            content="cat(b1)", kernel="R")
        #
        # test put variable with invalid names
        notebook.call(
            """\
            %put .a.b
            .a.b <- 22""",
            kernel="R",
            expect_error=True,
        )
        assert "22" == notebook.check_output("_a_b", kernel="SoS")

        #
        # test independence of variables
        notebook.call(
            """\
            %put my_var --to R
            my_var = '124'
            """,
            kernel="SoS",
        )
        assert "'124'" == notebook.check_output("my_var", kernel="R")

        notebook.call("my_var = 'something else'", kernel="R")
        assert "'124'" == notebook.check_output("my_var", kernel="SoS")

    def test_magic_sandbox(self, notebook):
        notebook.call(
            """\
            %sandbox
            with open('test_blah.txt', 'w') as tb:
                tb.write('a')
            """,
            kernel="SoS",
        )
        assert not os.path.isfile("test_blah.txt")

    def test_magic_save(self, notebook):
        tmp_file = os.path.join(os.path.expanduser("~"), "test_save.txt")
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        notebook.call(
            """\
            %save ~/test_save.txt
            a=1
            """,
            kernel="SoS",
        )
        with open(tmp_file) as tt:
            assert tt.read() == "a=1\n"
        os.remove(tmp_file)

    def test_magic_sessioninfo(self, notebook):
        output = notebook.check_output(
            """\
            %use Python3
            %use SoS
            %sessioninfo
            """,
            kernel="SoS",
        )
        assert "SoS Version" in output and "Python3" in output
        # test the with option
        notebook.call(
            '''
        sinfo = {
            'str_section': 'rsync 3.2',
            'list_section': [('v1', 'v2'), ('v3', b'v4')],
            'dict_section': {'d1': 'd2', 'd3': b'd4'}
        }
        ''',
            kernel='SoS')
        output = notebook.check_output(
            """\
            %use Python3
            %use SoS
            %sessioninfo --with sinfo
            """,
            kernel="SoS",
        )
        assert "SoS Version" in output and "Python3" in output
        assert all(
            x in output for x in ('rsync 3.2', 'v1', 'v2', 'v3', 'v4', 'd1',
                                  'd2', 'd3', 'd4'))

    def test_magic_set(self, notebook):
        assert "set" in notebook.check_output(
            """\
            %set
            %set -v2
            %set
            %set -v1
            """,
            kernel="SoS",
        )
        #
        # not accept workflow name
        assert "Magic %set cannot set positional argument" in notebook.check_output(
            "%set haha", kernel="SoS", expect_error=True)

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="! magic does not support built-in command #203")
    def test_magic_shell(self, notebook):
        assert "haha" in notebook.check_output("!echo haha", kernel="SoS")

    @pytest.mark.skip(
        reason="Cannot figure out why the file sometimes does not exist")
    def test_magic_sossave(self, notebook):
        #
        notebook.save()

        tmp_file = os.path.join(tempfile.gettempdir(), "test_sossave.html")
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
        assert "Workflow saved to" in notebook.check_output(
            f"""\
            %sossave {tmp_file} --force
            [10]
            print('kkk')
            """,
            kernel="SoS",
        )
        with open(tmp_file) as tt:
            assert "kkk" in tt.read()

    def test_magic_use(self, notebook):
        idx = notebook.call(
            "%use R0 -l sos_r.kernel:sos_R -c #CCCCCC", kernel="SoS")
        assert [204, 204, 204] == notebook.get_input_backgroundColor(idx)

        idx = notebook.call(
            "%use R1 -l sos_r.kernel:sos_R -k ir -c #CCCCCC", kernel="SoS")
        assert [204, 204, 204] == notebook.get_input_backgroundColor(idx)

        notebook.call("%use R2 -k ir", kernel="SoS")
        notebook.call("a <- 1024", kernel="R2")
        assert "1024" == notebook.check_output("a", kernel="R2")

        notebook.call("%use R3 -k ir -l R", kernel="SoS")
        notebook.call("a <- 233", kernel="R3")
        assert "233" == notebook.check_output("a", kernel="R3")

        notebook.call("%use R2 -c red", kernel="R3")
        assert "1024" == notebook.check_output("a", kernel="R2")

    def test_sos_vars(self, notebook):
        # test automatic tranfer of sos variables
        notebook.call("sosa = f'{3*8}'", kernel="Python3")
        assert "24" in notebook.check_output("sosa", kernel="SoS")

    def test_magic_with(self, notebook):
        # test %with
        notebook.call("a = 3", kernel="SoS")
        notebook.call(
            """\
            %with R -i a -o ran
            ran<-rnorm(a)
            """,
            kernel="SoS",
        )
        assert len(notebook.check_output("ran", kernel="SoS")) > 0
