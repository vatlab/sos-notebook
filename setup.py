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
from setuptools.command.install import install

# obtain version of SoS
with open('src/sos_notebook/_version.py') as version:
    for line in version:
        if line.startswith('__version__'):
            __version__ = eval(line.split('=')[1])
            break

kernel_json = {
    "argv":         ["python", "-m", "sos.jupyter.kernel", "-f", "{connection_file}"],
    "display_name": "SoS",
    "language":     "sos",
}

class InstallWithConfigurations(install):
    def run(self):
        # Regular installation
        install.do_egg_install(self)

        # at this point, jupyter and ipython should have been installed.
        import json
        try:
            from jupyter_client.kernelspec import KernelSpecManager as KS
        except ImportError:
            from ipykernel.kernelspec import KernelSpecManager as KS
        from IPython.utils.tempdir import TemporaryDirectory
        # Now write the kernelspec
        with TemporaryDirectory() as td:
            os.chmod(td, 0o755)  # Starts off as 700, not user readable
            shutil.copy('src/sos_notebook/kernel.js', os.path.join(td, 'kernel.js'))
            shutil.copy('src/sos_notebook/logo-64x64.png', os.path.join(td, 'logo-64x64.png'))
            with open(os.path.join(td, 'kernel.json'), 'w') as f:
                json.dump(kernel_json, f, sort_keys=True)
            try:
                KS().install_kernel_spec(td, 'sos', user=self.user, replace=True, prefix=sys.exec_prefix)
                log.info('Use "jupyter notebook" to create or open SoS notebooks.')
            except Exception:
                log.error("\nWARNING: Could not install SoS Kernel as %s user." % self.user)
        #log.info('Run "python misc/patch_spyder.py" to patch spyder with sos support.')
        log.info('\nSoS is installed and configured to use with Jupyter.')
        log.info('Use "set syntax=sos" to enable syntax highlighting.')
        log.info('And "sos -h" to start using Script of Scripts.')

dest = '''\
Exploratory data analysis in computationally intensive disciplines such as computational
biology often requires one to exploit a variety of tools implemented in different programming
languages and analyzing large datasets on high performance computing systems (e.g. computer
clusters). On top of all the difficulties in exchanging data between languages and computing
systems and analyzing data on different platforms, it becomes challenging to keep track of
such fragmented workflows and reproduce prior analyses.

With strong emphases on readability, practicality, and reproducibility, we have developed
a workflow system called "Script of Scripts" (SoS) with a web front-end and notebook format
based on Jupyter. Major features of SoS for exploratory analysis include multi-language
support, explicit and automatic data exchange between running sessions (kernels) in
different languages, cell-specific kernel switch using frontend-UI or cell magics,
a side-panel that allows scratch execution of statements, preview of files and expressions,
and line-by-line execution of statements in cells. In particular, variable and file preview
on the side panel makes it possible to trouble-shoot scripts in multiple languages without
contaminating the main notebook or interrupting the logic flow of the analysis. For large-scale
data analysis, the SoS workflow engine provides a unified interface to executing and managing
tasks on a variety of computing platforms such as PBS/Torch/LSF/Slurm clusters and RQ and
Celery task queues. Specified files are automatically synchronized between file systems,
thus enabling a single workflow to utilize multiple remote computing environments.

Researchers will benefit from the SoS system the flexibility to use their preferred languages
and tools for tasks without having to worry about data flow, and can perform light interactive
analysis while executing heavy remote tasks simultaneous in the same notebook in a neat and
organized fashion. SoS is available at http://vatlab.github.io/SOS/ and is distributed freely
under a GPL3 license. A live Jupyter server and several docker containers are available for
testing and running SoS without a local installation.

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
    cmdclass={'install': InstallWithConfigurations},
    install_requires=[
          'sos',
          'nbformat',
          'nbconvert>=5.1.1',
          'ipython',
          'ipykernel',
          'notebook>=5.0.0',
      ],
    entry_points= '''
[sos_previewers]
*.pdf,1 = sos_notebook.preview:preview_pdf
*.html,1 = sos_notebook.preview:preview_html
*.csv,1 = sos_notebook.preview:preview_csv
*.xls,1 = sos_notebook.preview:preview_xls
*.xlsx,1 = sos_notebook.preview:preview_xls
*.gz,1 = sos_notebook.preview:preview_gz
*.txt,1 = sos_notebook.preview:preview_txt
*.md,1 = sos_notebook.preview:preview_md [md]
*.dot,1 = sos_notebook.preview:preview_dot [dot]
imghdr:what,1 = sos_notebook.preview:preview_img [image]
zipfile:is_zipfile,1 = sos_notebook.preview:preview_zip
tarfile:is_tarfile,1 = sos_notebook.preview:preview_tar
*,0 = sos_notebook.preview:preview_txt

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

    extras_require = {
        'image':    ['wand'],
        'md':       ['markdown'],
    }
)
