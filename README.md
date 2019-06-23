[![PyPI version](https://badge.fury.io/py/sos-notebook.svg)](https://badge.fury.io/py/sos-notebook)
[![DOI](https://zenodo.org/badge/105826659.svg)](https://zenodo.org/badge/latestdoi/105826659)
[![Build Status](https://travis-ci.org/vatlab/sos-notebook.svg?branch=master)](https://travis-ci.org/vatlab/sos-notebook)
[![Build status](https://ci.appveyor.com/api/projects/status/nkyw7f4o97u7jl1l/branch/master?svg=true)](https://ci.appveyor.com/project/BoPeng/sos-notebook/branch/master)
[![Codacy Badge](https://api.codacy.com/project/badge/Grade/9b2c7f4e9d93434b8e5a33f7f91b8172)](https://www.codacy.com/app/BoPeng/sos-notebook?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=vatlab/sos-notebook&amp;utm_campaign=Badge_Grade)


# SoS Notebook

SoS Notebook is a [Jupyter](https://jupyter.org/) kernel that allows the use of multiple kernels in one Jupyter notebook.  Using language modules that understand datatypes of underlying languages (modules [sos-bash](https://github.com/vatlab/sos-bash), [sos-r](https://github.com/vatlab/sos-r), [sos-matlab](https://github.com/vatlab/sos-matlab), etc), SoS Notebook allows data exchange among live kernels of supported languages.

SoS Notebook also extends the Jupyter frontend and adds a console panel for the execution of scratch commands and display of intermediate results and progress information, and a number of shortcuts and magics to facilitate interactive data analysis. All these features have been ported to JupyterLab, either in the sos extension [jupyterlab-sos](https://github.com/vatlab/jupyterlab-sos) or contributed to JupyterLab as core features.

SoS Notebook also serves as the IDE for the [SoS Workflow](https://github.com/vatlab/sos) that allows the development and execution of workflows from Jupyter notebooks. This not only allows easy translation of scripts developed for interaction data analysis to workflows running in containers and remote systems, but also allows the creation of scientific workflows in a format with narratives, sample input and output.

SoS Notebook is part of the SoS suite of tools. Please refer to [SoS Homepage](http://vatlab.github.io/SoS/) for details about SoS, and [this page](https://vatlab.github.io/sos-docs/notebook.html#content) for documentations and examples on SoS Notebook. If a language that you are using is not yet supported by SoS, please [submit a ticket](https://github.com/vatlab/sos-notebook/issues), or consider adding a language module by yourself following the guideline [here](https://vatlab.github.io/sos-docs/doc/user_guide/language_module.html). 
