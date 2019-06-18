#!/usr/bin/env python
#
# Copyright (c) Bo Peng and the University of Texas MD Anderson Cancer Center
# Distributed under the terms of the 3-clause BSD License.

import os
import shutil
import sys
from distutils import log

from setuptools import find_packages, setup

_py_ver = sys.version_info
if _py_ver.major == 2 or (_py_ver.major == 3 and
                          (_py_ver.minor, _py_ver.micro) < (6, 0)):
    raise SystemError(
        'sos-notebook requires Python 3.6 or higher. Please upgrade your Python {}.{}.{}.'
        .format(_py_ver.major, _py_ver.minor, _py_ver.micro))

# obtain version of SoS
with open('src/sos_notebook/_version.py') as version:
    for line in version:
        if line.startswith('__version__'):
            __version__ = eval(line.split('=')[1])
            break

kernel_json = {
    "argv": ["python", "-m", "sos_notebook.kernel", "-f", "{connection_file}"],
    "display_name": "SoS",
    "language": "sos",
}

dest = '''\
Complex bioinformatic data analysis workflows involving multiple scripts
in different languages can be difficult to consolidate, share, and reproduce.
An environment that streamlines the entire data collection, analysis,
visualization and reporting processes of such multi-language analyses is
currently lacking.

We developed Script of Scripts (SoS) Notebook, an interactive data analysis
environment in which data from different scripting languages flow freely
within and across languages. SoS Notebook features a multi-language notebook
interface, a protocol for cross-language variable exchange, a preview engine
to visualize variables and common bioinformatic file formats, and a
report-generation tool to create dynamic documents from steps in different
languages. SoS Notebook enables researchers to perform sophisticated
bioinformatic analysis using the most suitable tools for different parts of
the workflow, without the limitations of a particular language or
complications of cross-language communications.

Please refer to http://vatlab.github.io/SOS/ for more details on SoS.
'''

setup(
    name="sos-notebook",
    version=__version__,
    description='Script of Scripts (SoS): an interactive, cross-platform, and cross-language workflow system for reproducible data analysis',
    long_description=dest,
    author='Bo Peng',
    url='https://github.com/vatlab/SOS',
    author_email='bpeng@mdanderson.org',
    maintainer='Bo Peng',
    maintainer_email='bpeng@mdanderson.org',
    license='3-clause BSD',
    include_package_data=True,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: Implementation :: CPython',
    ],
    zip_safe=False,
    packages=find_packages('src'),
    package_dir={'': 'src'},
    python_requires='>=3.6',
    install_requires=[
        'sos>=0.19.13',
        'nbformat',
        'nbconvert>=5.1.1',
        'ipython',
        'ipykernel',
        'notebook>=5.0.0',
        #'jupyter_contrib_nbextensions',
        'tabulate',
        #'markdown',
        'pandas',
        'numpy',
        #'selenium',
        #'requests',
        #'pytest',
        'psutil'
    ],
    entry_points='''
[sos_converters]
sos-ipynb.parser = sos_notebook.converter:get_script_to_notebook_parser
sos-ipynb.func = sos_notebook.converter:script_to_notebook

ipynb-sos.parser = sos_notebook.converter:get_notebook_to_script_parser
ipynb-sos.func = sos_notebook.converter:notebook_to_script

ipynb-html.parser = sos_notebook.converter:get_notebook_to_html_parser
ipynb-html.func = sos_notebook.converter:notebook_to_html

ipynb-pdf.parser = sos_notebook.converter:get_notebook_to_pdf_parser
ipynb-pdf.func = sos_notebook.converter:notebook_to_pdf

ipynb-md.parser = sos_notebook.converter:get_notebook_to_md_parser
ipynb-md.func = sos_notebook.converter:notebook_to_md

ipynb-ipynb.parser = sos_notebook.converter:get_notebook_to_notebook_parser
ipynb-ipynb.func = sos_notebook.converter:notebook_to_notebook

rmd-ipynb.parser = sos_notebook.converter:get_Rmarkdown_to_notebook_parser
rmd-ipynb.func = sos_notebook.converter:Rmarkdown_to_notebook
''')
