[![Anaconda-Server Badge](https://anaconda.org/conda-forge/sos-notebook/badges/version.svg)](https://anaconda.org/conda-forge/sos-notebook)
[![PyPI version](https://badge.fury.io/py/sos-notebook.svg)](https://badge.fury.io/py/sos-notebook)
[![DOI](https://zenodo.org/badge/105826659.svg)](https://zenodo.org/badge/latestdoi/105826659)
[![Build Status](https://travis-ci.org/vatlab/sos-notebook.svg?branch=master)](https://travis-ci.org/vatlab/sos-notebook)
[![Build status](https://ci.appveyor.com/api/projects/status/nkyw7f4o97u7jl1l/branch/master?svg=true)](https://ci.appveyor.com/project/BoPeng/sos-notebook/branch/master)

## ⚠️ Deprecation Notice

**The classic Jupyter notebook interface support for SoS Notebook has been deprecated.** 

This package no longer provides JavaScript extensions or frontend functionality for the classic Jupyter notebook interface. All frontend features have been migrated to JupyterLab and are available through [jupyterlab-sos](https://github.com/vatlab/jupyterlab-sos).

**This package is still required** as a backend dependency for jupyterlab-sos and contains the SoS kernel, magics, notebook converters (HTML, PDF, Markdown), and other core functionality. However, **for the best SoS experience, please use JupyterLab with the jupyterlab-sos extension**.

For more information, see the [JupyterLab SoS extension](https://github.com/vatlab/jupyterlab-sos).

# SoS Notebook

SoS Notebook is a [Jupyter](https://jupyter.org/) kernel that allows the use of multiple kernels in one Jupyter notebook.  Using language modules that understand datatypes of underlying languages (modules [sos-bash](https://github.com/vatlab/sos-bash), [sos-r](https://github.com/vatlab/sos-r), [sos-matlab](https://github.com/vatlab/sos-matlab), etc), SoS Notebook allows data exchange among live kernels of supported languages.

SoS Notebook also extends the Jupyter frontend and adds a console panel for the execution of scratch commands and display of intermediate results and progress information, and a number of shortcuts and magics to facilitate interactive data analysis. All these features have been ported to JupyterLab, either in the sos extension [jupyterlab-sos](https://github.com/vatlab/jupyterlab-sos) or contributed to JupyterLab as core features.

SoS Notebook also serves as the IDE for the [SoS Workflow](https://github.com/vatlab/sos) that allows the development and execution of workflows from Jupyter notebooks. This not only allows easy translation of scripts developed for interactive data analysis to workflows running in containers and remote systems, but also allows the creation of scientific workflows in a format with narratives, sample input and output.

SoS Notebook is part of the SoS suite of tools. Please refer to the [SoS Homepage](http://vatlab.github.io/SoS/) for details about SoS, and [this page](https://vatlab.github.io/sos-docs/notebook.html#content) for documentations and examples on SoS Notebook. If a language that you are using is not yet supported by SoS, please [submit a ticket](https://github.com/vatlab/sos-notebook/issues), or consider adding a language module by yourself following the guideline [here](https://vatlab.github.io/sos-docs/doc/user_guide/language_module.html).

## Installation

### For Users

Install from PyPI:
```bash
pip install sos-notebook
```

Install from conda-forge:
```bash
conda install -c conda-forge sos-notebook
```

### For Developers

SoS Notebook uses modern Python packaging and development tools. See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed development setup instructions.

Quick development setup:
```bash
# Prerequisites: Python 3.8+ and uv (https://github.com/astral-sh/uv)
git clone https://github.com/vatlab/sos-notebook.git
cd sos-notebook
invoke dev-setup    # Sets up virtual environment and dependencies
source .venv/bin/activate
```

## Development

This project uses modern Python development tools:
- **[uv](https://github.com/astral-sh/uv)** for fast dependency management and virtual environments
- **[ruff](https://github.com/astral-sh/ruff)** for linting and code formatting
- **[invoke](http://www.pyinvoke.org/)** for task automation
- **[pytest](https://pytest.org/)** for testing
- **Modern build system** with `pyproject.toml` (PEP 517/518)

### Quick Commands

```bash
# Set up development environment
invoke dev-setup

# Run quality checks
invoke check          # Run all checks (format, lint, test)
invoke format         # Format code with ruff
invoke lint --fix     # Lint and auto-fix issues
invoke test           # Run tests

# Build and release
invoke build          # Build distributions
invoke release-check  # Comprehensive pre-release checks
```

For detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Testing

The project includes comprehensive tests that run in Docker containers to simulate real Jupyter environments:

```bash
invoke test           # Quick tests (skip Docker/selenium)
invoke test-docker    # Full test suite in Docker (as in CI)
```

## License

This project is licensed under the 3-clause BSD License.
