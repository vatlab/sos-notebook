#!/usr/bin/env python3
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import shutil
import subprocess

import pytest


def test_script_to_and_from_notebook(sample_scripts):
    '''Test sos show script --notebook'''
    for script_file in sample_scripts:
        subprocess.call(
            f'sos convert {script_file} {script_file[:-4]}.ipynb',
            shell=True)
        subprocess.call(
            f'sos convert {script_file[:-4]}.ipynb {script_file}',
            shell=True)
        subprocess.call(
            f'sos convert {script_file[:-4]}.ipynb {script_file} --all',
            shell=True)

def test_convert_html(sample_notebook):
    subprocess.call(
        f'sos convert {sample_notebook} test_wf.html', shell=True)
    assert os.path.isfile('test_wf.html')
    # test the use of jupyter templates
    subprocess.call(
        f'sos convert {sample_notebook} test_wf1.html --template basic',
        shell=True)
    assert os.path.isfile('test_wf1.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf2.html --template sos-report',
        shell=True)
    assert os.path.isfile('test_wf2.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf3.html --template sos-full',
        shell=True)
    assert os.path.isfile('test_wf3.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf4.html --template sos-cm',
        shell=True)
    assert os.path.isfile('test_wf4.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf5.html --template sos-full-toc',
        shell=True)
    assert os.path.isfile('test_wf5.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf6.html --template sos-report-toc',
        shell=True)
    assert os.path.isfile('test_wf6.html')
    #
    subprocess.call(
        f'sos convert {sample_notebook} test_wf7.html --template sos-cm-toc',
        shell=True)
    assert os.path.isfile('test_wf7.html')

@pytest.mark.skipif(not shutil.which('xelatex'),
                   reason='No XeLatex under windows to compile pdf')
def test_convert_pdf(sample_notebook, sample_papermill_notebook):
    subprocess.call(
        f'sos convert {sample_notebook} test_wf.pdf', shell=True)
    assert os.path.isfile('test_wf.pdf')
    # PDF with execute
    subprocess.call(
        f'sos convert {sample_papermill_notebook} test_notebook.pdf --execute', shell=True)
    assert os.path.isfile('test_notebook.pdf')
    # mark down with execute
    subprocess.call(
        f'sos convert {sample_papermill_notebook} test_notebook_with_param.pdf --execute cutoff=34587', shell=True)
    assert os.path.isfile('test_notebook_with_param.pdf')
    with open('test_notebook_with_param.pdf', 'rb') as md:
        assert b'34587' in md.read()

def test_convert_md(sample_notebook, sample_papermill_notebook):
    subprocess.call(
        f'sos convert {sample_notebook} test_wf.md', shell=True)
    assert os.path.isfile('test_wf.md')
    # output to stdout
    subprocess.call(
        f'sos convert {sample_notebook} --to md > test_wf1.md',
        shell=True)
    assert os.path.isfile('test_wf1.md')
    # mark down with execute
    subprocess.call(
        f'sos convert {sample_papermill_notebook} test_notebook.md --execute', shell=True)
    assert os.path.isfile('test_notebook.md')
    # mark down with execute
    subprocess.call(
        f'sos convert {sample_papermill_notebook} test_notebook_with_param.md --execute cutoff=54321', shell=True)
    assert os.path.isfile('test_notebook_with_param.md')
    with open('test_notebook_with_param.md') as md:
        assert '54321' in md.read()

def test_convert_notebook(sample_notebook):
    assert subprocess.call(
        f'sos convert {sample_notebook} test_nonSoS.ipynb --kernel python3',
        shell=True) == 0
    assert os.path.isfile('test_nonSoS.ipynb')
    #
    assert subprocess.call(
        'sos convert test_nonSoS.ipynb test_SoS.ipynb', shell=True) == 0
    assert (os.path.isfile('test_SoS.ipynb'))
    # cannot convert to invalid kernel
    assert subprocess.call(
        f'sos convert {sample_notebook} test_invalid.ipynb --kernel nonexisting',
        shell=True) != 0

def test_execute_notebook(sample_papermill_notebook):
    assert subprocess.call(
        f'sos convert {sample_papermill_notebook} test_papermill_executed.ipynb --execute',
        shell=True) == 0
    assert os.path.isfile('test_papermill_executed.ipynb')
    #
    assert subprocess.call(
        f'sos convert {sample_papermill_notebook} test_papermill_executed_with_param.ipynb --execute cutoff=12345',
        shell=True) == 0
    assert os.path.isfile('test_papermill_executed_with_param.ipynb')
    with open('test_papermill_executed_with_param.ipynb') as nb:
        assert '12345' in nb.read()

def test_execute_and_convert(sample_papermill_notebook):
    assert subprocess.call(
        f'sos convert {sample_papermill_notebook} test_papermill_executed.html --execute',
        shell=True) == 0
    assert os.path.isfile('test_papermill_executed.html')
    #
    assert subprocess.call(
        f'sos convert {sample_papermill_notebook} test_papermill_executed_with_param.html --execute cutoff=12345',
        shell=True) == 0
    assert os.path.isfile('test_papermill_executed_with_param.html')
    with open('test_papermill_executed_with_param.html') as nb:
        assert '12345' in nb.read()

def test_comments(sample_notebook):
    '''Test if comments before section headers are correctly extracted'''
    subprocess.call(
        f'sos convert {sample_notebook} sample_workflow.sos', shell=True)
    with open('sample_workflow.sos') as sw:
        wf = sw.read()
    assert 'this is a test workflow' not in wf
    assert wf.count('this comment will be included but not shown in help') == 1
    assert wf.count('this comment will become the comment for parameter b') == 1
    assert wf.count('this comment will become the comment for parameter d') == 1
    assert 'this is a cell with another kernel' not in wf
    assert 'this comment will not be included in exported workflow' not in wf
