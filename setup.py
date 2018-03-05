#!/usr/bin/env python
#
# This file is part of Script of Scripts (sos), a workflow system
# for the execution of commands and scripts in different languages.
# Please visit https://github.com/vatlab/SOS for more information.
#
# Copyright (C) 2016 Bo Peng (bpeng@mdanderson.org)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#

import sys, os
import shutil
from setuptools import find_packages, setup
from distutils import log

_py_ver = sys.version_info
if _py_ver.major == 2 or (_py_ver.major == 3 and (_py_ver.minor, _py_ver.micro) < (6, 0)):
    raise SystemError('sos-notebook requires Python 3.6 or higher. Please upgrade your Python {}.{}.{}.'
        .format(_py_ver.major, _py_ver.minor, _py_ver.micro))

# obtain version of SoS
with open('src/sos_notebook/_version.py') as version:
    for line in version:
        if line.startswith('__version__'):
            __version__ = eval(line.split('=')[1])
            break

kernel_json = {
    "argv":         ["python", "-m", "sos_notebook.kernel", "-f", "{connection_file}"],
    "display_name": "SoS",
    "language":     "sos",
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

setup(name = "sos-notebook",
    version = __version__,
    description = 'Script of Scripts (SoS): an interactive, cross-platform, and cross-language workflow system for reproducible data analysis',
    long_description=dest,
    author = 'Bo Peng',
    url = 'https://github.com/vatlab/SOS',
    author_email = 'bpeng@mdanderson.org',
    maintainer = 'Bo Peng',
    maintainer_email = 'bpeng@mdanderson.org',
    license = 'GPL3',
    include_package_data = True,
    classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Natural Language :: English',
        'Operating System :: POSIX :: Linux',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Intended Audience :: Information Technology',
        'Intended Audience :: Science/Research',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: Implementation :: CPython',
        ],
    packages = find_packages('src'),
    package_dir = {'': 'src'},
    install_requires=[
          'sos>=0.9.12.8',
          'nbformat',
          'nbconvert>=5.1.1',
          'ipython',
          'ipykernel',
          'notebook>=5.0.0',
          'tabulate',
          'wand',
          'markdown',
      ],
    entry_points= '''
[sos_functions]
runfile = sos_notebook.workflow_executor:runfile

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
''',
#
#[sos_installers]
#kernel.parser = sos_notebook.install:get_install_sos_kernel_spec_parser
#kernel.func = sos_notebook.install:install_sos_kernel_spec
    extras_require = {
        'dot':      ['graphviz']
    }
)
