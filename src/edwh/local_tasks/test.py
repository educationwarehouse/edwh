"""Default pytest test runner with coverage support."""

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ewok import Context, task
from termcolor import cprint

from .. import confirm
from ..meta import pip_install


def find_pytest() -> str | None:
    """Find pytest in the project virtualenv first, then on PATH."""
    venv_pytest = Path("./venv/bin/pytest")
    if venv_pytest.is_file() and os.access(venv_pytest, os.X_OK):
        return str(venv_pytest)

    return shutil.which("pytest")


def has_pytest_cov(pytest: str) -> bool:
    """Check whether the selected pytest executable can load pytest-cov."""
    python = Path(pytest).resolve().with_name("python")
    if not python.is_file():
        return False

    result = subprocess.run(
        [str(python), "-c", "import pytest_cov"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def install_test_dependencies(c: Context) -> bool:
    """Offer to install the test extra into edwh's own environment."""
    if not confirm("Test dependencies are missing. Install edwh[test] now? [Yn] ", default=True):
        return False

    pip_install(c, "edwh[test]")
    return True


@task(
    flags={
        "keyword_search": ("keyword-search", "k"),
        "exitfirst": ("exitfirst", "x"),
    },
)
def run(
    c: Context,
    directory: str = ".",
    keyword_search: str = "",
    verbose: bool = False,
    exitfirst: bool = False,
    coverage: bool = True,
    html: bool = False,
) -> None:
    """Run pytest with coverage by default."""
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

    command = [pytest, directory]
    if coverage:
        command.append(f"--cov={directory}")
    if html:
        command.append("--cov-report=html")
    if verbose:
        command.append("-v")
    if exitfirst:
        command.append("-x")
    if keyword_search:
        command.extend(("-k", keyword_search))

    c.run(shlex.join(command), pty=sys.stdout.isatty())
