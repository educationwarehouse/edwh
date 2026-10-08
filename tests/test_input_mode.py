"""
EDWH_INPUT_MODE: interactive input, unattended defaults, or unattended input reporting.
"""

import json
from pathlib import Path

import pytest

from src.edwh.cli import program
from src.edwh.helpers import (
    confirm,
    get_input_mode,
    interactive_selected_checkbox_values,
    interactive_selected_radio_value,
    is_non_interactive,
    looks_secret,
    missing_required_input,
)
from src.edwh.tasks import check_env, read_dotenv


@pytest.fixture(autouse=True)
def clean_input_env(monkeypatch):
    for key in ("EDWH_INPUT_MODE", "EDWH_NON_INTERACTIVE", "EDWH_FROM_ENV"):
        monkeypatch.delenv(key, raising=False)


def reported(capsys) -> dict:
    """The missing_input payload written to stderr."""
    return json.loads(capsys.readouterr().err.strip().splitlines()[-1])


# -- mode resolution --------------------------------------------------------------------------


def test_defaults_to_interactive():
    assert get_input_mode() == "interactive"
    assert not is_non_interactive()


def test_legacy_flag_means_defaults(monkeypatch):
    monkeypatch.setenv("EDWH_NON_INTERACTIVE", "1")
    assert get_input_mode() == "defaults"
    assert is_non_interactive()


@pytest.mark.parametrize("mode", ["interactive", "defaults", "required"])
def test_input_mode_beats_legacy_flag(monkeypatch, mode):
    monkeypatch.setenv("EDWH_NON_INTERACTIVE", "1")
    monkeypatch.setenv("EDWH_INPUT_MODE", mode)
    assert get_input_mode() == mode
    assert is_non_interactive() == (mode != "interactive")


def test_unknown_input_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "yolo")
    with pytest.raises(ValueError, match="EDWH_INPUT_MODE"):
        get_input_mode()


# -- reporting --------------------------------------------------------------------------------


def test_missing_required_input_reports_json_and_exits_78(tmp_path: Path, capsys):
    with pytest.raises(SystemExit) as exit_info:
        missing_required_input("DB_PASSWORD", "database password", secret=True, env_path=tmp_path / ".env")

    assert exit_info.value.code == 78
    assert reported(capsys) == {
        "status": "missing_input",
        "key": "DB_PASSWORD",
        "secret": True,
        "prompt": "database password",
        "env_path": str((tmp_path / ".env").resolve()),
    }


def test_missing_required_input_without_env_path(capsys):
    with pytest.raises(SystemExit):
        missing_required_input("SELECTION", "pick one")

    assert "env_path" not in reported(capsys)


@pytest.mark.parametrize("key", ["DB_PASSWORD", "api_key", "JWT_SECRET", "GITHUB_TOKEN", "HASH_SALT"])
def test_looks_secret(key):
    assert looks_secret(key)


@pytest.mark.parametrize("key", ["HOSTINGDOMAIN", "PGPORT", "COMPOSE_PROJECT_NAME"])
def test_looks_not_secret(key):
    assert not looks_secret(key)


# -- confirm ----------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["defaults", "required"])
def test_non_strict_confirm_uses_default(monkeypatch, mode):
    monkeypatch.setenv("EDWH_INPUT_MODE", mode)
    assert confirm("sure?", default=True) is True
    assert confirm("sure?", default=False) is False


def test_strict_confirm_raises_in_defaults_mode(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "defaults")
    with pytest.raises(RuntimeError):
        confirm("sure?", strict=True)


def test_strict_confirm_reports_in_required_mode(monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    with pytest.raises(SystemExit) as exit_info:
        confirm("sure?", strict=True)

    assert exit_info.value.code == 78
    assert reported(capsys)["key"] == "CONFIRMATION"


# -- selections -------------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["defaults", "required"])
def test_checkbox_returns_preselected_values(monkeypatch, mode):
    monkeypatch.setenv("EDWH_INPUT_MODE", mode)
    assert interactive_selected_checkbox_values(["a", "b", "c"], selected=["a", "c"]) == ["a", "c"]


def test_checkbox_without_selection_in_defaults_mode(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "defaults")
    assert interactive_selected_checkbox_values(["a", "b"]) == []
    assert interactive_selected_checkbox_values(["a", "b"], allow_empty=True) is None


def test_checkbox_without_selection_reports_in_required_mode(monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    with pytest.raises(SystemExit) as exit_info:
        interactive_selected_checkbox_values(["a", "b"], prompt="which?")

    assert exit_info.value.code == 78
    payload = reported(capsys)
    assert (payload["key"], payload["prompt"]) == ("SELECTION", "which?")


def test_checkbox_may_stay_empty_in_required_mode(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    assert interactive_selected_checkbox_values(["a", "b"], allow_empty=True) is None


@pytest.mark.parametrize("mode", ["defaults", "required"])
def test_radio_returns_preselected_value(monkeypatch, mode):
    monkeypatch.setenv("EDWH_INPUT_MODE", mode)
    assert interactive_selected_radio_value({1: "one", 2: "two"}, selected=2) == 2


def test_radio_without_selection_in_defaults_mode(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "defaults")
    assert interactive_selected_radio_value(["a", "b"]) is None


def test_radio_without_selection_reports_in_required_mode(monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    with pytest.raises(SystemExit) as exit_info:
        interactive_selected_radio_value(["a", "b"], prompt="which one?")

    assert exit_info.value.code == 78
    assert reported(capsys)["prompt"] == "which one?"


def test_radio_may_stay_empty_in_required_mode(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    assert interactive_selected_radio_value(["a", "b"], allow_empty=True) is None


# -- check_env --------------------------------------------------------------------------------


def test_check_env_required_uses_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    env_path = tmp_path / ".env"

    assert check_env("PGPORT", "5432", "a port", env_path=env_path) == "5432"
    assert read_dotenv(env_path)["PGPORT"] == "5432"


def test_check_env_required_keeps_existing_value(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    env_path = tmp_path / ".env"
    env_path.write_text("PGPORT=6543\n")

    assert check_env("PGPORT", None, "a port", env_path=env_path) == "6543"


def test_check_env_required_reports_missing_value(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    env_path = tmp_path / ".env"

    with pytest.raises(SystemExit) as exit_info:
        check_env("DB_PASSWORD", None, "database password", env_path=env_path)

    assert exit_info.value.code == 78
    assert reported(capsys) == {
        "status": "missing_input",
        "key": "DB_PASSWORD",
        "secret": True,
        "prompt": "database password",
        "env_path": str(env_path.resolve()),
    }
    assert "DB_PASSWORD" not in read_dotenv(env_path)


def test_check_env_required_reports_empty_existing_value(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    env_path = tmp_path / ".env"
    env_path.write_text("HOSTINGDOMAIN=\n")

    with pytest.raises(SystemExit):
        check_env("HOSTINGDOMAIN", None, "domain", env_path=env_path)

    assert reported(capsys)["key"] == "HOSTINGDOMAIN"


def test_check_env_secret_is_guessed_from_key(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")

    with pytest.raises(SystemExit):
        check_env("HOSTINGDOMAIN", None, "domain", env_path=tmp_path / ".env")

    assert reported(capsys)["secret"] is False


@pytest.mark.parametrize(("key", "secret"), [("HOSTINGDOMAIN", True), ("DB_PASSWORD", False)])
def test_check_env_explicit_secret_beats_guess(tmp_path: Path, monkeypatch, capsys, key, secret):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")

    with pytest.raises(SystemExit):
        check_env(key, None, "something", env_path=tmp_path / ".env", secret=secret)

    assert reported(capsys)["secret"] is secret


def test_check_env_from_env_reports_instead_of_raising_in_required_mode(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    monkeypatch.setenv("EDWH_FROM_ENV", "1")
    monkeypatch.delenv("API_TOKEN", raising=False)

    with pytest.raises(SystemExit) as exit_info:
        check_env("API_TOKEN", None, "token", env_path=tmp_path / ".env")

    assert exit_info.value.code == 78
    assert reported(capsys)["key"] == "API_TOKEN"


def test_check_env_from_env_reads_environment_in_required_mode(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    monkeypatch.setenv("EDWH_FROM_ENV", "1")
    monkeypatch.setenv("API_TOKEN", "abc")

    assert check_env("API_TOKEN", None, "token", env_path=tmp_path / ".env") == "abc"


# -- cli --------------------------------------------------------------------------------------


def parsed_kwargs(*argv: str) -> dict[str | None, dict]:
    """Parse `edwh <argv>` up to (not including) execution."""
    program.create_config()
    program.parse_core(["edwh", *argv])
    program.parse_collection()
    program.parse_tasks()
    return {context.name: context.as_kwargs for context in program.tasks}


def test_setup_stays_interactive_by_default():
    assert parsed_kwargs("setup")["setup"]["non_interactive"] is False


@pytest.mark.parametrize("mode", ["defaults", "required"])
def test_unattended_mode_makes_setup_non_interactive(monkeypatch, mode):
    monkeypatch.setenv("EDWH_INPUT_MODE", mode)
    assert parsed_kwargs("setup")["setup"]["non_interactive"] is True


def test_explicit_non_interactive_flag_is_kept(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    assert parsed_kwargs("setup", "--non-interactive")["setup"]["non_interactive"] is True


def test_only_the_setup_task_is_marked(monkeypatch):
    monkeypatch.setenv("EDWH_INPUT_MODE", "required")
    kwargs = parsed_kwargs("worktree.setup", "setup")

    assert "non_interactive" not in kwargs["worktree.setup"]
    assert kwargs["setup"]["non_interactive"] is True
