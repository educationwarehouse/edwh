from contextlib import chdir

from edwh.tasks import TomlConfig


def test_toml_config_bootstrap_preserves_application_context(tmp_path):
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
