import typing as t
from pathlib import Path

# file.seek(_, whence), 'whence' can be one of:
FILE_START = 0
FILE_RELATIVE = 1
FILE_END = 2

DOCKER_COMPOSE = "docker --log-level error compose"  # used to be docker-compose. includes in docker-compose requires
DEFAULT_TOML_NAME = ".toml"  # was config.toml
FALLBACK_TOML_NAME = "default.toml"
LEGACY_TOML_NAME = "config.toml"  # set to None when no longer supported
DEFAULT_DOTENV_PATH = Path(".env")

type AnyDict = dict[str, t.Any]
