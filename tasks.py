"""
Development tasks for sos-notebook using invoke.
"""

import os
import sys
from pathlib import Path

from invoke import task


def check_tool(ctx, tool_name):
    """Check if a tool is available."""
    result = ctx.run(f"which {tool_name}", warn=True, hide=True)
    return result.ok


# Project paths
ROOT_DIR = Path(__file__).parent
SRC_DIR = ROOT_DIR / "src"
TEST_DIR = ROOT_DIR / "test"


@task
def format(ctx, check=False):
    """Format code with ruff."""
    if not check_tool(ctx, "ruff"):
        print("❌ ruff not found. Install with: uv add --dev ruff")
        sys.exit(1)

    paths = [str(SRC_DIR), str(TEST_DIR), "tasks.py"]

    if check:
        print("🔍 Checking code formatting...")
        cmd = "ruff format --check " + " ".join(paths)
    else:
        print("🎨 Formatting code...")
        cmd = "ruff format " + " ".join(paths)

    result = ctx.run(cmd, warn=True)

    if check and result.ok:
        print("✅ Code formatting is correct!")
    elif check:
        print("⚠️  Code formatting needs changes")
    else:
        print("✅ Code formatting complete!")


@task
def lint(ctx, fix=False):
    """Run linting with ruff."""
    if not check_tool(ctx, "ruff"):
        print("❌ ruff not found. Install with: uv add --dev ruff")
        sys.exit(1)

    paths = [str(SRC_DIR), str(TEST_DIR), "tasks.py"]

    if fix:
        print("🔧 Running ruff linting with auto-fix...")
        cmd = "ruff check --fix " + " ".join(paths)
    else:
        print("🔍 Running ruff linting...")
        cmd = "ruff check " + " ".join(paths)

    result = ctx.run(cmd, warn=True)

    if result.ok:
        print("✅ Linting passed!")
    else:
        print(
            "❌ Linting issues found. Run 'invoke lint --fix' or 'invoke format' to fix issues."
        )
        sys.exit(1)


@task
def typecheck(ctx, strict=False):
    """Run type checking with mypy."""
    if not check_tool(ctx, "mypy"):
        print("❌ mypy not found. Install with: uv add --dev mypy")
        sys.exit(1)

    print("🔍 Running type checking...")
    result = ctx.run("mypy src/", warn=True)

    if result.ok:
        print("✅ Type checking passed!")
    elif strict:
        print("❌ Type checking issues found.")
        sys.exit(1)
    else:
        print(
            "⚠️  Type checking found issues, but continuing (run with --strict to fail on errors)"
        )
        print("💡 Type annotations are present for IDE support and documentation")


@task
def precommit(ctx, install=False):
    """Run pre-commit hooks."""
    if install:
        print("📋 Installing pre-commit hooks...")
        ctx.run("pre-commit install")
        print("✅ Pre-commit hooks installed!")
    else:
        print("🔍 Running pre-commit checks...")
        ctx.run("pre-commit run --all-files")


@task
def test(ctx, path="", verbose=False, coverage=False):
    """Run tests with pytest."""
    if not path:
        path = str(TEST_DIR)

    cmd = ["python", "-m", "pytest"]

    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    if coverage:
        cmd.extend(
            [
                "--cov=sos_notebook",
                "--cov-report=term-missing",
                "--cov-report=html:htmlcov",
            ]
        )
        print("🧪 Running tests with coverage...")
    else:
        print("🧪 Running tests...")

    cmd.append(path)

    # Skip tests that require selenium/Docker if not available
    cmd.extend(["-k", "not test_frontend", "--disable-warnings"])

    result = ctx.run(" ".join(cmd), warn=True)

    if result.ok:
        print("✅ All tests passed!")
        if coverage:
            print("📊 Coverage report generated in htmlcov/")
    else:
        print("❌ Some tests failed!")
        sys.exit(1)


@task
def test_docker(ctx):
    """Run full test suite in Docker (as done in CI)."""
    print("🐳 Running tests in Docker environment...")
    print("This requires Docker to be running and may take some time...")

    # Check if docker-compose is available
    result = ctx.run("docker-compose --version", warn=True, hide=True)
    if not result.ok:
        print(
            "❌ docker-compose not available. Install Docker and docker-compose first."
        )
        sys.exit(1)

    # Run the Docker test setup similar to CI
    with ctx.cd("development"):
        print("🔧 Setting up Docker environment...")
        ctx.run("docker network create sosnet", warn=True)
        # Set project name for consistent container naming
        os.environ["COMPOSE_PROJECT_NAME"] = "sosnotebook"
        ctx.run("docker-compose up -d")

        # Copy project and run tests (Docker Compose V2 uses hyphens)
        ctx.run("docker cp .. sosnotebook-sos-notebook-1:/home/jovyan/sos-notebook")
        ctx.run(
            "docker exec -u root sosnotebook-sos-notebook-1 bash -c 'cd /home/jovyan/sos-notebook && sh development/install_sos_notebook.sh'"
        )

        print("🧪 Running tests in container...")
        result = ctx.run(
            "docker exec sosnotebook-sos-notebook-1 bash -c 'cd /home/jovyan/sos-notebook/test && pytest -v'",
            warn=True,
        )

        # Cleanup
        print("🧹 Cleaning up Docker environment...")
        ctx.run("docker-compose down", warn=True)

        if result.ok:
            print("✅ Docker tests passed!")
        else:
            print("❌ Docker tests failed!")
            sys.exit(1)


@task
def build(ctx, clean=False):
    """Build source and wheel distributions."""
    if clean:
        print("🧹 Cleaning build artifacts...")
        ctx.run("rm -rf build/ dist/ src/*.egg-info/")

    print("📦 Building distributions...")
    ctx.run("python -m build")
    print("✅ Build complete! Check dist/ directory.")


@task
def clean(ctx, all=False):
    """Clean build artifacts and caches."""
    patterns = [
        "build/",
        "dist/",
        "src/*.egg-info/",
        "**/__pycache__/",
        "**/*.pyc",
        "**/*.pyo",
        ".coverage",
        "htmlcov/",
        ".pytest_cache/",
    ]

    if all:
        patterns.extend(
            [
                ".tox/",
                "**/.ipynb_checkpoints/",
            ]
        )
        print("🧹 Deep cleaning all build artifacts and caches...")
    else:
        print("🧹 Cleaning build artifacts...")

    for pattern in patterns:
        ctx.run(f"find . -name '{pattern}' -exec rm -rf {{}} +", warn=True)

    print("✅ Cleanup complete!")


@task
def install(ctx, dev=True, force=False):
    """Install the package."""
    if dev:
        print("📦 Installing in development mode...")
        cmd = "uv pip install -e ."
    else:
        print("📦 Installing package...")
        cmd = "uv pip install ."

    if force:
        cmd += " --force-reinstall"

    ctx.run(cmd)
    print("✅ Installation complete!")


@task
def check(ctx):
    """Run all quality checks (format, lint, typecheck, test)."""
    print("🔍 Running comprehensive quality checks...")
    print("\n" + "=" * 50)
    print("1. Code Formatting Check")
    print("=" * 50)
    format(ctx, check=True)

    print("\n" + "=" * 50)
    print("2. Linting Check")
    print("=" * 50)
    lint(ctx)

    print("\n" + "=" * 50)
    print("3. Type Checking")
    print("=" * 50)
    typecheck(ctx)

    print("\n" + "=" * 50)
    print("4. Running Tests")
    print("=" * 50)
    test(ctx)

    print("\n" + "=" * 50)
    print("✅ All quality checks passed!")
    print("=" * 50)


@task
def release_check(ctx):
    """Run comprehensive checks before release."""
    print("🚀 Running release checks...")

    # Run quality checks
    check(ctx)

    print("\n" + "=" * 50)
    print("4. Build Check")
    print("=" * 50)
    build(ctx, clean=True)

    print("\n" + "=" * 50)
    print("✅ All release checks passed!")
    print("🚀 Ready for release!")
    print("=" * 50)


@task
def uv_sync(ctx):
    """Sync dependencies using uv."""
    print("🔄 Syncing dependencies with uv...")
    ctx.run("uv sync")
    print("✅ Dependencies synced!")


@task
def uv_lock(ctx):
    """Update uv.lock file."""
    print("🔒 Updating uv.lock file...")
    ctx.run("uv lock")
    print("✅ Lock file updated!")


@task
def venv_create(ctx):
    """Create virtual environment with uv."""
    print("🏗️  Creating virtual environment with uv...")
    ctx.run("uv venv")
    print("✅ Virtual environment created!")
    print("💡 Activate with: source .venv/bin/activate")


@task
def dev_setup(ctx):
    """Set up development environment."""
    print("🛠️  Setting up development environment...")

    # Create virtual environment if it doesn't exist
    if not os.path.exists(".venv"):
        print("🏗️  Creating virtual environment...")
        ctx.run("uv venv")

    # Install development dependencies
    print("📦 Installing development dependencies...")
    ctx.run("uv pip install -e .")
    ctx.run("uv sync --dev")

    # Set up pre-commit
    print("📋 Setting up pre-commit hooks...")
    precommit(ctx, install=True)

    print("✅ Development environment setup complete!")
    print("\nCommon commands:")
    print("  invoke --list        # Show all available tasks")
    print("  invoke check         # Run all quality checks")
    print("  invoke format        # Format code with ruff")
    print("  invoke lint          # Run linting with ruff")
    print("  invoke lint --fix    # Run linting with auto-fix")
    print("  invoke test          # Run tests")
    print("\n💡 Don't forget to activate the virtual environment:")
    print("  source .venv/bin/activate")


@task(default=True)
def help(ctx):
    """Show help and available tasks."""
    print("SoS Notebook Development Tasks")
    print("=" * 40)
    ctx.run("invoke --list")
    print("\nFor detailed help on any task:")
    print("  invoke --help TASKNAME")
