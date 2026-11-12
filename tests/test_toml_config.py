from contextlib import chdir
from pathlib import Path

import pytest

from src.edwh.tasks import TomlConfig


def test_toml_config_bootstrap_preserves_application_context(tmp_path: Path) -> None:
    """Loading a fallback config must not lose ewok's application context."""
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "default.toml").write_text(
        """[services]
services = []
minimal = []
include_celeries_in_minimal = false
include_pgq_in_minimal = false
log = []
db = []
"""
    )

    with chdir(tmp_path):
        config = TomlConfig.load(cache=False)

    assert config is not None
    assert (tmp_path / ".toml").exists()


def test_toml_config_exits_cleanly_when_setup_cannot_create_services(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """If `ew setup` can't produce [services], stop with a hint instead of a KeyError.

    Mirrors the real failure: a compose label needs a variable that .env doesn't set yet,
    so `docker compose config` fails inside setup and [services] is never written.
    """
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  web:\n    image: scratch\n    labels:\n      - 'host=${EDWH_TEST_UNSET_VARIABLE:?required}'\n"
    )
    (tmp_path / ".toml").write_text("[dotenv]\npath = '.env'\n")

    with chdir(tmp_path), pytest.raises(SystemExit) as exc:
        TomlConfig.load(cache=False)

    assert exc.value.code == 1
    assert "[services]" in capsys.readouterr().out
