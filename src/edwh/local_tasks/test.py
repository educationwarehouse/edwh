"""Default pytest test runner with coverage support."""

import os
import shlex
import shutil
import subprocess
import sys
from importlib.metadata import requires
from importlib.util import find_spec
from pathlib import Path

from ewok import Context, task
from termcolor import cprint

from .. import confirm
from ..meta import pip_install
from ..release_backend import PYPROJECT, _load, _nested

# The one place a project says which code is its own.
COVERAGE_KEY = ("tool", "edwh", "test", "directory")


def find_pytest() -> str | None:
    """Find pytest in the project virtualenv first, then on PATH."""
    venv_pytest = Path("./venv/bin/pytest")
    if venv_pytest.is_file() and os.access(venv_pytest, os.X_OK):
        return str(venv_pytest)

    if pytest := shutil.which("pytest"):
        return pytest

    if find_spec("pytest"):
        return f"{sys.executable} -m pytest"

    return None


def has_pytest_cov(pytest: str) -> bool:
    """Check whether the selected pytest executable can load pytest-cov."""
    python = Path(shlex.split(pytest)[0]).resolve().with_name("python")
    if not python.is_file():
        return False

    result = subprocess.run(
        [str(python), "-c", "import pytest_cov"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def edwh_test_extra_requirements() -> list[str]:
    """Return the requirements declared by edwh's ``test`` extra."""
    return [
        requirement.split(";", maxsplit=1)[0].strip()
        for requirement in requires("edwh") or []
        if 'extra == "test"' in requirement or "extra == 'test'" in requirement
    ]


def coverage_directory(directory: str, override: str = "", pyproject: Path = PYPROJECT) -> str:
    """
    What to measure coverage over, which is not always what to run tests from.

    A src-layout project runs its tests from `.` but only cares about `src/`;
    `--cov=.` would drag in tests, task files and the virtualenv. Explicit flag
    wins, then `[tool.edwh.test] directory`, then the test directory.
    """
    if override:
        return override

    if isinstance(configured := _nested(_load(pyproject), COVERAGE_KEY), str) and configured:
        return configured

    return directory


def install_test_dependencies(c: Context) -> bool:
    """Offer to install the test extra into edwh's own environment."""
    if not confirm("Test dependencies are missing. Install edwh[test] now? [Yn] ", default=True):
        return False

    pip_install(c, *edwh_test_extra_requirements())
    return True


@task(
    flags={
        "keyword_search": ("keyword-search", "k"),
        "exitfirst": ("exitfirst", "x"),
        "cov_directory": ("cov-directory", "coverage-directory"),
    },
)
def run(
    c: Context,
    directory: str = ".",
    cov_directory: str = "",
    keyword_search: str = "",
    verbose: bool = False,
    exitfirst: bool = False,
    coverage: bool = True,
    html: bool = False,
) -> None:
    """
    Run pytest with coverage by default.

    `directory` is where tests are collected from; coverage is measured over
    `--cov-directory`, `[tool.edwh.test] directory`, or `directory` -- in that
    order.
    """
    pytest = find_pytest()
    if not pytest:
        if not install_test_dependencies(c):
            cprint("pytest is not installed.", "red", file=sys.stderr)
            raise SystemExit(1)
        pytest = find_pytest()
        if not pytest:
            cprint(
                "pytest was installed but cannot be found; please run this command again.",
                "yellow",
                file=sys.stderr,
            )
            raise SystemExit(1)

    if coverage and not has_pytest_cov(pytest):
        if not install_test_dependencies(c):
            cprint("Coverage requires pytest-cov, or run with `--no-coverage`.", "red", file=sys.stderr)
            raise SystemExit(1)
        if not has_pytest_cov(pytest):
            cprint(
                "pytest-cov was installed but is not available to the selected pytest; please run this command again.",
                "yellow",
                file=sys.stderr,
            )
            raise SystemExit(1)

    command = [*shlex.split(pytest), directory]
    if coverage:
        command.append(f"--cov={coverage_directory(directory, cov_directory)}")
    if html:
        command.append("--cov-report=html")
    if verbose:
        command.append("-v")
    if exitfirst:
        command.append("-x")
    if keyword_search:
        command.extend(("-k", keyword_search))

    c.run(shlex.join(command), pty=sys.stdout.isatty())
