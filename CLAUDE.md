# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

**Invoke Tasks (Recommended):**
- `invoke --list` - Show all available development tasks
- `invoke dev-setup` - Set up complete development environment with uv
- `invoke venv-create` - Create virtual environment with uv
- `invoke uv-sync` - Sync dependencies using uv
- `invoke uv-lock` - Update uv.lock file
- `invoke check` - Run all quality checks (format, lint, test)
- `invoke format` - Format code with ruff
- `invoke format --check` - Check code formatting without changes
- `invoke lint` - Run linting with ruff
- `invoke lint --fix` - Run linting with auto-fix
- `invoke typecheck` - Run type checking with mypy (warnings only)
- `invoke typecheck --strict` - Run type checking with strict enforcement
- `invoke test` - Run tests with pytest
- `invoke test --verbose` - Run tests with verbose output
- `invoke test --coverage` - Run tests with coverage report
- `invoke build` - Build source and wheel distributions
- `invoke build --clean` - Clean build artifacts and rebuild
- `invoke clean` - Clean build artifacts and caches
- `invoke install` - Install package in development mode
- `invoke release-check` - Run comprehensive pre-release checks
- `invoke test-docker` - Run full test suite in Docker (CI environment)

**uv Virtual Environment Management:**
- `uv venv` - Create virtual environment
- `uv sync` - Install dependencies from pyproject.toml
- `uv sync --dev` - Install with development dependencies
- `uv add <package>` - Add runtime dependency
- `uv add --dev <package>` - Add development dependency
- `uv remove <package>` - Remove dependency
- `uv lock` - Update dependency lock file
- `uv pip install -e .` - Install package in development mode
- `source .venv/bin/activate` - Activate virtual environment

**Direct Commands:**
- `pytest -v` - Run all tests (executed in Docker container)
- `docker exec sosnotebook_sos-notebook_1 bash -c 'cd test && pytest -v'` - Full test run in CI environment

**Code Quality:**
- `pre-commit run --all-files` - Run code formatting and linting (ruff)
- `ruff check` - Run linting
- `ruff check --fix` - Run linting with auto-fix
- `ruff format` - Format code
- `ruff format --check` - Check code formatting
- `mypy src/` - Run type checking with mypy

**Development Environment:**
- Uses Docker for testing - see `development/docker-compose.yml`
- `docker-compose build --no-cache` - Rebuild test images
- `docker network create sosnet` - Create Docker network for testing

**Build System:**
- Uses modern `pyproject.toml` configuration (PEP 517/518)
- `python -m build` - Build source and wheel distributions
- `python -m build --sdist` - Build source distribution only
- `python -m build --wheel` - Build wheel distribution only
- `pip install -e .` - Install in development mode
- Package entry points defined in pyproject.toml for SoS converters
- Old `setup.py` kept as `setup.py.old` for reference

## Architecture Overview

SoS Notebook is a Jupyter kernel that enables multi-language workflows within a single notebook. The architecture consists of several key components:

**Core Kernel System:**
- `kernel.py` - Main `SoS_Kernel` class extending `IPythonKernel`, handles cell execution and communication
- `subkernel.py` - `Subkernels` class manages multiple language kernels (R, Bash, Python, etc.)
- `comm_manager.py` - `SoSCommManager` handles inter-kernel communication and data exchange

**Language Integration:**
- Language modules (sos-bash, sos-r, etc.) provide language-specific data type understanding
- `magics.py` - SoS-specific Jupyter magic commands for workflow control
- `completer.py` - Tab completion for SoS syntax and cross-language variables

**Workflow Execution:**
- `step_executor.py` - Executes individual workflow steps
- `workflow_executor.py` - Orchestrates complete workflows, includes `NotebookLoggingHandler`
- Supports both interactive execution and batch workflow processing

**Conversion System:**
- `converter.py` - Multiple converters for different formats:
  - `ScriptToNotebookConverter` (sos-ipynb)
  - `NotebookToScriptConverter` (ipynb-sos)
  - `NotebookToHTMLConverter` (ipynb-html)
  - `NotebookToPDFConverter` (ipynb-pdf)
  - `NotebookToMarkdownConverter` (ipynb-md)

**Testing Strategy:**
- Integration tests in Docker containers simulate real Jupyter environment
- Tests cover frontend interaction, magic commands, conversions, and workflows
- Sample notebooks in `test/` directory provide test scenarios

**Key Dependencies:**
- Requires Python ≥3.7, built on jupyter ecosystem (jupyter_client, ipykernel, nbformat)
- Core SoS package (sos>=0.22.0) provides workflow engine
- pandas/numpy for data handling, psutil for system monitoring

**Data Exchange:**
The system enables seamless data transfer between kernels through SoS variable system, supporting dataframes, matrices, and other structured data types across R, Python, Bash, and other supported languages.