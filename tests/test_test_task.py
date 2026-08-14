"""
Which directory `test.run` measures coverage over.
"""

from pathlib import Path

from src.edwh.local_tasks.test import coverage_directory

CONFIGURED = """[project]
name = "demo"

[tool.edwh.test]
directory = "src"
"""


def write(tmp_path: Path, content: str) -> Path:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(content)
    return pyproject


def test_falls_back_to_test_directory(tmp_path):
    assert coverage_directory(".", pyproject=tmp_path / "nope.toml") == "."


def test_configured_directory_is_used(tmp_path):
    assert coverage_directory(".", pyproject=write(tmp_path, CONFIGURED)) == "src"


def test_flag_beats_config(tmp_path):
    assert coverage_directory(".", "tests", pyproject=write(tmp_path, CONFIGURED)) == "tests"


def test_unusable_config_value_is_ignored(tmp_path):
    pyproject = write(tmp_path, '[project]\nname = "demo"\n\n[tool.edwh.test]\ndirectory = []\n')
    assert coverage_directory(".", pyproject=pyproject) == "."
