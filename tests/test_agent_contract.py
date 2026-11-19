"""
The contract for non-human callers (CI, the MCP plugin, coding agents):
`$EDWH_RESULT_FILE`, `require_virtualenv` and `SudoRequired`.
"""

import json
import os
import subprocess
import sys
import textwrap
import typing as t
from pathlib import Path

import invoke
import keyring
import pytest
from ewok import Context

from src.edwh import tasks as edwh_tasks
from src.edwh.helpers import (
    MAX_RESULT_MESSAGE,
    RESULT_FILE_ENV,
    SudoRequired,
    TaskAborted,
    VirtualenvRequired,
    write_task_result,
)
from src.edwh.tasks import project_virtualenv, require_sudo, require_virtualenv

EDWH = Path(sys.executable).with_name("edwh")


@pytest.fixture
def result_file(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "result.json"
    monkeypatch.setenv(RESULT_FILE_ENV, str(path))
    return path


def read(path: Path) -> dict:
    return json.loads(path.read_text())


# -- write_task_result ------------------------------------------------------------------------


def test_nothing_is_written_without_env(monkeypatch):
    monkeypatch.delenv(RESULT_FILE_ENV, raising=False)
    assert write_task_result("lint", ok=True) is False


def test_result_is_written(result_file):
    assert write_task_result("lint", ok=True, result={"a": 1})
    assert read(result_file) == {"task": "lint", "ok": True, "result": {"a": 1}, "error": None}


def test_first_write_wins(result_file):
    write_task_result("lint", ok=False, result={"first": True})
    assert write_task_result("lint", ok=True) is False
    assert read(result_file)["result"] == {"first": True}


def test_empty_file_is_overwritten(result_file):
    result_file.write_text("")
    assert write_task_result("lint", ok=True)


def test_aborted_task_reports_type_and_hint(result_file):
    write_task_result("setup", ok=False, error=SudoRequired("needs sudo", hint="run `edwh sudo`"))
    assert read(result_file)["error"] == {"type": "sudo_required", "message": "needs sudo", "hint": "run `edwh sudo`"}


def test_other_errors_are_truncated(result_file):
    write_task_result("x", ok=False, error=RuntimeError("a" * (MAX_RESULT_MESSAGE + 100)))
    error = read(result_file)["error"]
    assert error["type"] == "failed"
    assert error["message"].endswith(" [truncated]")
    assert len(error["message"]) < MAX_RESULT_MESSAGE + 20


def test_config_proxies_are_serialized_as_dicts(result_file):
    ctx = invoke.Context()
    ctx.result = {"results": {"ruff": True}}
    write_task_result("lint", ok=True, result={"results": ctx.result["results"]})
    assert read(result_file)["result"] == {"results": {"ruff": True}}


def test_aborted_tasks_still_exit_with_code_1():
    error = VirtualenvRequired("no venv")
    assert isinstance(error, SystemExit)
    assert isinstance(error, TaskAborted)
    assert error.code == 1


def local_context() -> Context:
    return t.cast(Context, invoke.Context())


# -- require_virtualenv -----------------------------------------------------------------------


def make_venv(directory: Path, name: str = "venv") -> Path:
    venv = directory / name
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text("home = /usr/bin\n")
    return venv


def test_no_project_venv_is_fine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert project_virtualenv() is None
    require_virtualenv(local_context())


@pytest.mark.parametrize("name", ["venv", ".venv"])
def test_project_venv_is_detected(tmp_path, name):
    venv = make_venv(tmp_path, name)
    assert project_virtualenv(tmp_path) == venv


def test_directory_without_pyvenv_cfg_is_not_a_venv(tmp_path):
    (tmp_path / "venv").mkdir()
    assert project_virtualenv(tmp_path) is None


def test_running_outside_project_venv_stops(tmp_path, monkeypatch):
    venv = make_venv(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(VirtualenvRequired) as raised:
        require_virtualenv(local_context())

    assert str(venv) in raised.value.message
    assert f"{venv}/bin/edwh" in (raised.value.hint or "")


def test_running_from_project_venv_is_fine(tmp_path, monkeypatch):
    venv = make_venv(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "prefix", str(venv))
    require_virtualenv(local_context())


# -- require_sudo -----------------------------------------------------------------------------


@pytest.fixture
def no_stored_sudo(monkeypatch):
    monkeypatch.setattr(edwh_tasks, "use_configured_ssh_agent_keyring", lambda: None)
    monkeypatch.setattr(keyring, "get_password", lambda *_: None)


def sudo_unavailable_context() -> Context:
    """A context where `sudo --non-interactive` fails, like on a machine without cached sudo credentials."""
    return t.cast(Context, invoke.MockContext(run={"sudo --non-interactive echo ''": invoke.Result(exited=1)}))


@pytest.mark.usefixtures("no_stored_sudo")
def test_unattended_sudo_raises_sudo_required(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "defaults")

    with pytest.raises(SudoRequired) as raised:
        require_sudo(sudo_unavailable_context())

    assert "edwh sudo" in (raised.value.hint or "")


@pytest.mark.usefixtures("no_stored_sudo")
def test_sudo_without_terminal_raises_sudo_required(monkeypatch):
    monkeypatch.delenv("EDWH_INPUT_MODE", raising=False)
    monkeypatch.setattr(edwh_tasks, "has_controlling_terminal", lambda: False)

    with pytest.raises(SudoRequired):
        require_sudo(sudo_unavailable_context())


# -- the CLI writes the result file -----------------------------------------------------------

PROJECT_TASKS = """
from edwh import SudoRequired, task


@task()
def works(c):
    return {"answer": 42}


@task()
def soft_fail(c):
    return {"ok": False, "reason": "nope"}


@task()
def needs_sudo(c):
    raise SudoRequired("needs sudo", hint="run `edwh sudo`")


@task()
def crashes(c):
    raise RuntimeError("boom")
"""


def run_edwh(project: Path, *argv: str) -> tuple[int, dict | None]:
    result_file = project / "result.json"
    result_file.unlink(missing_ok=True)
    process = subprocess.run(
        [str(EDWH), *argv],
        cwd=project,
        env={**_clean_env(), RESULT_FILE_ENV: str(result_file)},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    return process.returncode, read(result_file) if result_file.exists() else None


def _clean_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if not key.startswith("EDWH_")}


@pytest.fixture
def project(tmp_path) -> Path:
    (tmp_path / "tasks.py").write_text(textwrap.dedent(PROJECT_TASKS))
    return tmp_path


@pytest.mark.skipif(not EDWH.is_file(), reason="needs an installed edwh executable")
class TestCli:
    def test_return_value_is_reported(self, project):
        code, result = run_edwh(project, "local.works")
        assert code == 0
        assert result == {"task": "local.works", "ok": True, "result": {"answer": 42}, "error": None}

    def test_returning_ok_false_marks_failure(self, project):
        _, result = run_edwh(project, "local.soft-fail")
        assert result is not None
        assert result["ok"] is False
        assert result["result"]["reason"] == "nope"

    def test_sudo_required_is_reported(self, project):
        code, result = run_edwh(project, "local.needs-sudo")
        assert code == 1
        assert result is not None
        assert result["error"]["type"] == "sudo_required"

    def test_crash_is_reported(self, project):
        code, result = run_edwh(project, "local.crashes")
        assert code != 0
        assert result is not None
        assert result["ok"] is False
        assert result["error"] == {"type": "failed", "message": "boom", "hint": None}

    def test_lint_reports_per_tool_results(self, project):
        (project / "bad.py").write_text("import os\n")
        code, result = run_edwh(project, "lint", "--output", "ci")
        assert code == 1  # findings fail the command in every output mode
        assert result is not None
        assert result["error"] is None  # lint itself ran fine
        assert result["task"] == "lint"
        assert result["ok"] is False
        assert result["result"]["results"]["linting (ruff)"] is False

    def test_lint_outside_project_venv_is_reported(self, project):
        make_venv(project)
        code, result = run_edwh(project, "lint")
        assert code == 1
        assert result is not None
        assert result["error"]["type"] == "virtualenv_required"


def test_stored_password_works_without_stdin(monkeypatch):
    """With the password in the keyring, unattended sudo must not depend on (an empty) stdin."""
    monkeypatch.setattr(edwh_tasks, "use_configured_ssh_agent_keyring", lambda: None)
    monkeypatch.setattr(keyring, "get_password", lambda *_: "secret")
    monkeypatch.setenv("EDWH_INPUT_MODE", "defaults")
    ctx = sudo_unavailable_context()

    assert require_sudo(ctx) is True
    assert ctx.config.sudo.password == "secret"
    assert ctx.config.run.in_stream is False
