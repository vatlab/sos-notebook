#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import shutil
import subprocess
import unittest


class TestConvert(unittest.TestCase):

    def setUp(self):
        # self.olddir = os.getcwd()
        # file_dir = os.path.split(__file__)[0]
        # if file_dir:
        #     os.chdir(file_dir)
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
        self.scripts = ['temp/script1.sos', 'temp/script2.sos']

    def tearDown(self):
        shutil.rmtree('temp')
        # os.chdir(self.olddir)

    def testScriptToAndFromNotebook(self):
        '''Test sos show script --notebook'''
        for script_file in self.scripts:
            subprocess.call(
                f'sos convert {script_file} {script_file[:-4]}.ipynb',
                shell=True)
            subprocess.call(
                f'sos convert {script_file[:-4]}.ipynb {script_file}',
                shell=True)

    def testConvertHTML(self):
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf.html', shell=True)
        self.assertTrue(os.path.isfile('test_wf.html'))
        # test the use of jupyter templates
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf1.html --template basic',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf1.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf2.html --template sos-report',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf2.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf3.html --template sos-full',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf3.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf4.html --template sos-cm',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf4.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf5.html --template sos-full-toc',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf5.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf6.html --template sos-report-toc',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf6.html'))
        #
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf7.html --template sos-cm-toc',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf7.html'))

    @unittest.skipIf(not shutil.which('xelatex'),
                     'No XeLatex under windows to compile pdf')
    def testConvertPDF(self):
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf.pdf', shell=True)
        self.assertTrue(os.path.isfile('test_wf.pdf'))
        # PDF with execute
        subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_notebook.pdf --execute', shell=True)
        self.assertTrue(os.path.isfile('test_notebook.pdf'))
        # mark down with execute
        subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_notebook_with_param.pdf --execute cutoff=34587', shell=True)
        self.assertTrue(os.path.isfile('test_notebook_with_param.pdf'))
        with open('test_notebook_with_param.pdf', 'rb') as md:
            assert b'34587' in md.read()

    def testConvertMD(self):
        subprocess.call(
            'sos convert sample_notebook.ipynb test_wf.md', shell=True)
        self.assertTrue(os.path.isfile('test_wf.md'))
        # output to stdout
        subprocess.call(
            'sos convert sample_notebook.ipynb --to md > test_wf1.md',
            shell=True)
        self.assertTrue(os.path.isfile('test_wf1.md'))
        # mark down with execute
        subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_notebook.md --execute', shell=True)
        self.assertTrue(os.path.isfile('test_notebook.md'))
        # mark down with execute
        subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_notebook_with_param.md --execute cutoff=54321', shell=True)
        self.assertTrue(os.path.isfile('test_notebook_with_param.md'))
        with open('test_notebook_with_param.md') as md:
            assert '54321' in md.read()

    def testConvertNotebook(self):
        ret = subprocess.call(
            'sos convert sample_notebook.ipynb test_nonSoS.ipynb --kernel python3',
            shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_nonSoS.ipynb'))
        #
        ret = subprocess.call(
            'sos convert test_nonSoS.ipynb test_SoS.ipynb', shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_SoS.ipynb'))
        # cannot convert to invalid kernel
        ret = subprocess.call(
            'sos convert sample_notebook.ipynb test_invalid.ipynb --kernel nonexisting',
            shell=True)
        self.assertNotEqual(ret, 0)

    def testExecuteNotebook(self):
        ret = subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_papermill_executed.ipynb --execute',
            shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_papermill_executed.ipynb'))
        #
        ret = subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_papermill_executed_with_param.ipynb --execute cutoff=12345',
            shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_papermill_executed_with_param.ipynb'))
        with open('test_papermill_executed_with_param.ipynb') as nb:
            assert '12345' in nb.read()

    def testExecuteAndConvert(self):
        ret = subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_papermill_executed.html --execute',
            shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_papermill_executed.html'))
        #
        ret = subprocess.call(
            'sos convert sample_papermill_notebook.ipynb test_papermill_executed_with_param.html --execute cutoff=12345',
            shell=True)
        self.assertEqual(ret, 0)
        self.assertTrue(os.path.isfile('test_papermill_executed_with_param.html'))
        with open('test_papermill_executed_with_param.html') as nb:
            assert '12345' in nb.read()

    def testComments(self):
        '''Test if comments before section headers are correctly extracted'''
        subprocess.call(
            'sos convert sample_workflow.ipynb sample_workflow.sos', shell=True)
        with open('sample_workflow.sos') as sw:
            wf = sw.read()
        self.assertFalse('this is a test workflow' in wf)
        self.assertEqual(
            wf.count('this comment will be included but not shown in help'), 1)
        self.assertTrue(
            wf.count('this comment will become the comment for parameter b'), 1)
        self.assertTrue(
            wf.count('this comment will become the comment for parameter d'), 1)
        self.assertFalse('this is a cell with another kernel' in wf)
        self.assertFalse(
            'this comment will not be included in exported workflow' in wf)


if __name__ == '__main__':
    unittest.main()
