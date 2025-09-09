# Contributing to SoS Notebook

Thank you for your interest in contributing to SoS Notebook! This document provides comprehensive guidelines for setting up your development environment, making changes, and submitting contributions.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Code Quality](#code-quality)
- [Testing](#testing)
- [Building and Releasing](#building-and-releasing)
- [Submitting Changes](#submitting-changes)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

1. **Python 3.8+** - SoS Notebook requires Python 3.8 or later
2. **[uv](https://github.com/astral-sh/uv)** - Fast Python package installer and resolver
   ```bash
   # Install uv (recommended method)
   curl -LsSf https://astral.sh/uv/install.sh | sh
   
   # Or via pip
   pip install uv
   
   # Or via homebrew (macOS)
   brew install uv
   ```
3. **Git** - For version control
4. **Docker** (optional) - For running the full test suite

### Verify Installation

```bash
python --version  # Should be 3.8+
uv --version     # Should be 0.4.0+
git --version
```

## Development Setup

### 1. Clone the Repository

```bash
git clone https://github.com/vatlab/sos-notebook.git
cd sos-notebook
```

### 2. Set Up Development Environment

We use `invoke` for task automation. The `dev-setup` command will:
- Create a virtual environment with uv
- Install the package in development mode
- Install all development dependencies
- Set up pre-commit hooks

```bash
# One-command setup
invoke dev-setup

# Activate the virtual environment
source .venv/bin/activate
```

### 3. Manual Setup (Alternative)

If you prefer manual setup:

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install package in development mode with dependencies
uv pip install -e .
uv sync --dev

# Install pre-commit hooks
pre-commit install
```

### 4. Verify Setup

```bash
# List available development tasks
invoke --list

# Run a quick check
invoke format --check
invoke lint
```

## Development Workflow

### Daily Development Commands

```bash
# Activate virtual environment (if not already active)
source .venv/bin/activate

# Make your changes...

# Format code
invoke format

# Check and fix linting issues
invoke lint --fix

# Run tests
invoke test

# Run all quality checks
invoke check
```

### Task Automation with Invoke

We use [invoke](http://www.pyinvoke.org/) for development task automation. All tasks are defined in `tasks.py`.

#### Core Tasks

```bash
# Environment management
invoke dev-setup          # Complete development setup
invoke venv-create         # Create virtual environment
invoke uv-sync            # Sync dependencies
invoke uv-lock            # Update lock file

# Code quality
invoke format             # Format code with ruff
invoke format --check     # Check formatting without changes
invoke lint               # Run linting
invoke lint --fix         # Run linting with auto-fix
invoke check              # Run all quality checks (format, lint, test)

# Testing
invoke test               # Run tests (skips Docker/selenium tests)
invoke test --verbose     # Verbose test output
invoke test --coverage    # Run tests with coverage report
invoke test-docker        # Full test suite in Docker (CI environment)

# Building
invoke build              # Build source and wheel distributions
invoke build --clean      # Clean and rebuild
invoke clean              # Clean build artifacts
invoke install            # Install package in development mode

# Release
invoke release-check      # Comprehensive pre-release checks
```

#### Advanced Tasks

```bash
# Run specific test paths
invoke test --path="test/test_magics.py"

# Generate coverage report
invoke test --coverage

# Clean everything
invoke clean --all
```

## Code Quality

### Code Formatting and Linting

We use [ruff](https://github.com/astral-sh/ruff) for both code formatting and linting. Ruff is extremely fast and replaces multiple tools (yapf, flake8, isort, etc.).

#### Configuration

Ruff is configured in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py38"
line-length = 88

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501"]  # line too long (handled by formatter)

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
```

#### Running Code Quality Checks

```bash
# Format code
invoke format

# Check formatting without making changes
invoke format --check

# Run linting
invoke lint

# Auto-fix linting issues
invoke lint --fix

# Run all quality checks
invoke check
```

### Pre-commit Hooks

Pre-commit hooks are automatically installed during `invoke dev-setup`. They run on every commit to ensure code quality:

- Code formatting with ruff
- Linting with ruff
- Basic file checks (trailing whitespace, file size, etc.)

To run pre-commit manually:
```bash
pre-commit run --all-files
```

## Testing

### Test Structure

- `test/` - Main test directory
- `test/test_*.py` - Unit and integration tests
- Docker-based integration tests simulate real Jupyter environments

### Running Tests

```bash
# Quick tests (skip Docker/selenium dependencies)
invoke test

# Verbose output
invoke test --verbose

# Run with coverage
invoke test --coverage

# Run specific test file
invoke test --path="test/test_magics.py"

# Full test suite in Docker (as run in CI)
invoke test-docker
```

### Test Dependencies

Some tests require additional dependencies:
- **Selenium** - For frontend integration tests
- **Docker** - For containerized testing environment
- **ImageMagick** - For image processing tests

These are automatically skipped if not available, with appropriate skip messages.

### Writing Tests

- Follow pytest conventions
- Use the `NotebookTest` base class for kernel tests
- Mock external dependencies when possible
- Add integration tests for new features

## Building and Releasing

### Modern Build System

SoS Notebook uses a modern Python build system based on:
- `pyproject.toml` for project configuration (PEP 517/518)
- `uv` for dependency management
- `build` module for creating distributions

### Building Distributions

```bash
# Build both source and wheel distributions
invoke build

# Clean build artifacts first
invoke build --clean

# Manual build (alternative)
uv run python -m build
```

### Release Preparation

Before releasing:

```bash
# Run comprehensive pre-release checks
invoke release-check

# This runs:
# 1. All quality checks (format, lint, test)
# 2. Clean build
# 3. Distribution verification
```

### Version Management

1. Update version in `pyproject.toml`
2. Update version in `src/sos_notebook/_version.py`
3. Update `CHANGELOG.md` (if exists)
4. Run `invoke release-check`
5. Create git tag and push

## Submitting Changes

### Pull Request Process

1. **Fork the repository** on GitHub
2. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the development workflow
4. **Run quality checks**:
   ```bash
   invoke check
   ```
5. **Commit your changes** with descriptive messages:
   ```bash
   git add .
   git commit -m "Add feature: description of changes"
   ```
6. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
7. **Create a Pull Request** on GitHub

### Commit Message Guidelines

- Use clear, descriptive commit messages
- Start with a verb in present tense ("Add", "Fix", "Update", "Remove")
- Limit first line to 72 characters
- Reference issues when applicable: "Fix #123: description"

### Pull Request Guidelines

- **Title**: Clear, descriptive title
- **Description**: Explain what changes were made and why
- **Testing**: Describe how the changes were tested
- **Documentation**: Update documentation if needed
- **Breaking Changes**: Clearly mark any breaking changes

## Project Structure

```
sos-notebook/
├── src/sos_notebook/          # Main package source
│   ├── __init__.py
│   ├── kernel.py              # Main SoS kernel
│   ├── subkernel.py          # Multi-language kernel management
│   ├── magics.py             # Jupyter magic commands
│   ├── converter.py          # Notebook conversion utilities
│   └── ...
├── test/                     # Test suite
│   ├── test_kernel.py
│   ├── test_magics.py
│   └── ...
├── development/              # Docker development environment
├── tasks.py                  # Invoke task definitions
├── pyproject.toml           # Project configuration
├── uv.lock                  # Dependency lock file
├── README.md                # Project overview
├── CONTRIBUTING.md          # This file
└── CLAUDE.md               # Claude Code development guide
```

### Key Files

- **`pyproject.toml`** - Modern Python project configuration
- **`tasks.py`** - Development task automation with invoke
- **`uv.lock`** - Locked dependency versions for reproducible builds
- **`CLAUDE.md`** - Development guidance for Claude Code AI assistant

## Troubleshooting

### Common Issues

#### Virtual Environment Issues
```bash
# Remove and recreate virtual environment
rm -rf .venv
invoke venv-create
source .venv/bin/activate
invoke uv-sync
```

#### Dependency Issues
```bash
# Update dependencies
invoke uv-sync

# Regenerate lock file
invoke uv-lock
```

#### Import Errors
```bash
# Reinstall package in development mode
uv pip install -e .
```

#### Test Failures
```bash
# Run tests with verbose output
invoke test --verbose

# Run specific test file
invoke test --path="test/test_specific.py"

# Skip Docker tests if Docker isn't available
invoke test  # Docker tests are skipped automatically
```

### Performance Issues

- **Slow dependency resolution**: uv is much faster than pip, but if you experience issues, try clearing cache: `uv cache clean`
- **Slow tests**: Use `invoke test` instead of `invoke test-docker` for faster iteration

### Getting Help

1. **Check existing issues**: [GitHub Issues](https://github.com/vatlab/sos-notebook/issues)
2. **Search documentation**: [SoS Documentation](https://vatlab.github.io/sos-docs/)
3. **Create a new issue**: Include:
   - Python version (`python --version`)
   - uv version (`uv --version`)
   - Operating system
   - Full error message
   - Steps to reproduce

## Development Philosophy

- **Modern tooling**: We use the latest and fastest Python development tools
- **Developer experience**: Commands should be simple and fast
- **Code quality**: Automated formatting and linting
- **Testing**: Comprehensive tests including Docker-based integration tests
- **Documentation**: Clear documentation for users and developers

Thank you for contributing to SoS Notebook! 🎉