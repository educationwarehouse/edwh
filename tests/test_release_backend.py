# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT
"""
Which release tool owns a project, and whether we can pin that choice.
"""

import inspect

import pytest

from src.edwh.release_backend import (
    detect_backend,
    enable_publishing,
    pin_backend,
    pinned_backend,
    psr_uploaded,
    vommit_publishes,
)

PSR = """[project]
name = "demo"

[tool.semantic_release]
branch = "main"
version_variable = "src/demo/__about__.py:__version__"
upload_to_repository = false
"""

VOMMIT = """[project]
name = "demo"
version = "1.0.0"

[tool.vommit]
prerelease_token = "beta"
"""


def write(tmp_path, content: str):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return pyproject


def test_detects_psr_config(tmp_path):
    assert detect_backend(write(tmp_path, PSR)) == "psr"


def test_detects_vommit_config(tmp_path):
    assert detect_backend(write(tmp_path, VOMMIT)) == "vommit"


def test_project_without_release_config_needs_setup(tmp_path):
    assert detect_backend(write(tmp_path, '[project]\nname = "demo"\n')) == "none"


def test_missing_pyproject_needs_setup(tmp_path):
    assert detect_backend(tmp_path / "pyproject.toml") == "none"


def test_malformed_pyproject_does_not_raise(tmp_path):
    """A broken pyproject is the build backend's problem to report, not ours."""
    assert detect_backend(write(tmp_path, "[project\nname = ")) == "none"


def test_pin_stops_the_migration_offer(tmp_path):
    """Answering 'never' has to survive into the next release."""
    pyproject = write(tmp_path, PSR)
    pin_backend("psr", pyproject)

    assert pinned_backend(pyproject) == "psr"
    assert detect_backend(pyproject) == "psr"


def test_vommit_config_beats_a_stale_psr_pin(tmp_path):
    """Migrating by hand should not also require removing the opt-out."""
    pyproject = write(tmp_path, VOMMIT + '\n[tool.edwh.release]\nbackend = "psr"\n')

    assert detect_backend(pyproject) == "vommit"


def test_pin_to_vommit_without_config_asks_for_setup(tmp_path):
    """Pinned to vommit but never configured: offer setup, don't fall back to psr."""
    pyproject = write(tmp_path, PSR)
    pin_backend("vommit", pyproject)

    assert detect_backend(pyproject) == "none"


def test_pin_preserves_comments_and_is_idempotent(tmp_path):
    pyproject = write(tmp_path, '# keep me\n[project]\nname = "demo" # and me\n')

    pin_backend("psr", pyproject)
    once = pyproject.read_text()
    pin_backend("psr", pyproject)

    assert "# keep me" in once
    assert "# and me" in once
    assert pyproject.read_text() == once


def test_pin_alongside_existing_tool_edwh_table(tmp_path):
    """[tool.edwh.lint] is the established neighbour; don't clobber it."""
    pyproject = write(tmp_path, '[project]\nname = "demo"\n\n[tool.edwh.lint]\nty = false\n')
    pin_backend("psr", pyproject)

    text = pyproject.read_text()
    assert "ty = false" in text
    assert pinned_backend(pyproject) == "psr"


@pytest.mark.parametrize(
    "table,uploaded",
    [
        ("", True),  # no psr config: nothing was disabled
        ("[tool.semantic_release]\nbranch = 'main'\n", True),  # v7 defaulted to true
        ("[tool.semantic_release]\nupload_to_repository = false\n", False),
        ("[tool.semantic_release]\nupload_to_pypi = false\n", False),
    ],
)
def test_psr_uploaded(tmp_path, table, uploaded):
    """Read before migrating: vommit strips the table it is derived from."""
    assert psr_uploaded(write(tmp_path, f'[project]\nname = "demo"\n\n{table}')) is uploaded


def test_enable_publishing_restores_the_step_migration_removed(tmp_path):
    """psr wasn't uploading because plugin.release was; vommit owns that now."""
    pyproject = write(tmp_path, VOMMIT + "\n[tool.vommit.pypi]\nenabled = false\n")
    assert vommit_publishes(pyproject) is False

    enable_publishing(pyproject)

    assert vommit_publishes(pyproject) is True


def test_publishing_defaults_to_on_without_a_pypi_section(tmp_path):
    assert vommit_publishes(write(tmp_path, VOMMIT)) is True


def test_vommit_tasks_accept_the_arguments_we_pass():
    """
    `vommit.tasks` is excluded from vommit's coverage, so it is the surface most
    likely to be reshaped. Fail here rather than at someone's release.
    """
    vommit_tasks = pytest.importorskip("vommit.tasks")

    expected = {
        "setup": {"project_dir"},
        "migrate": {"project_dir"},
        "bump": {"major", "minor", "patch", "prerelease", "noop"},
        "release": {"major", "minor", "patch", "prerelease", "noop", "yes"},
    }

    for name, arguments in expected.items():
        task = getattr(vommit_tasks, name)
        parameters = set(inspect.signature(task.body).parameters)
        assert arguments <= parameters, f"vommit.tasks.{name} lost {arguments - parameters}"
