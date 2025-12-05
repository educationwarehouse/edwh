import contextlib
import datetime as dt
import fnmatch
import hashlib
import io
import json
import os
import pathlib
import re
import shlex
import shutil
import sys
import threading
import time
import traceback
import typing
import warnings
from collections import defaultdict
from concurrent import futures
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Optional

import ewok
import invoke
import keyring
import tabulate
import tomlkit  # has more features than tomllib
import yaml
from dotenv import dotenv_values
from ewok import Task, format_frame, task
from invoke import Promise, Runner
from invoke.context import Context
from rapidfuzz import fuzz
from termcolor import colored, cprint
from termcolor._types import Color
from typing_extensions import Never

from .__about__ import __version__ as edwh_version
from .constants import (
    DEFAULT_DOTENV_PATH,
    DEFAULT_TOML_NAME,
    DOCKER_COMPOSE,
    FALLBACK_TOML_NAME,
    FILE_START,
    LEGACY_TOML_NAME,
)
from .discover import discover, get_hosts_for_service  # noqa F401 - import for export (Remco afblijven)
from .health import (  # noqa F401 - import for export
    docker_inspect,
    find_container_ids,
    find_containers_ids,
    get_healths,
)

# noinspection PyUnresolvedReferences
# ^ keep imports for backwards compatibility (e.g. `from edwh.tasks import executes_correctly`)
from .helpers import (  # noqa F401 - import for export
    AnyDict,
    ColorFn,
    LineBufferHandler,
    NoopHandler,
    confirm,
    dc_config,
    dump_set_as_list,
    executes_correctly,
    execution_fails,
    fabric_read,
    fabric_write,
    flatten,
    interactive_selected_checkbox_values,
    interactive_selected_radio_value,
    noop,
    parse_regex,
    print_aligned,
    rainbow,
    run_pty,
    run_pty_ok,
    shorten,
)
from .helpers import generate_password as _generate_password

# noinspection PyUnresolvedReferences
# ^ keep imports for other tasks to register them!
from .meta import is_installed, plugins, self_update  # noqa


def copy_fallback_toml(
    tomlfile: str | Path = DEFAULT_TOML_NAME,
    fallbacks: typing.Collection[str | Path] = (LEGACY_TOML_NAME, FALLBACK_TOML_NAME),
    force: bool = False,
) -> bool:
    tomlfile_path = Path(tomlfile)

    if tomlfile_path.exists() and not force:
        return False

    for fallback_name in fallbacks:
        fallback_path = Path(fallback_name)

        if fallback_name is None or not fallback_path.exists():
            continue

        shutil.copy(fallback_path, tomlfile_path)
        return True

    tomlfile_path.touch()
    return False


def service_names(
    service_arg: typing.Collection[str] | None,
    default: typing.Literal["all", "minimal", "logs", "celeries"] | None = None,
) -> list[str]:
    """
    Returns a list of matching servicenames based on ALL_SERVICES. filename globbing is applied.

    Use service_names(['*celery*','pg*']) to select all celery services, and all of pg related instances.
    :param service_arg: list of services or service selectors using wildcards
    :param default: which services to return if service_arg is empty?
    :return: list of unique services names that match the given list
    """

    config = TomlConfig.load()
    if not config:
        return []

    selected = set()
    if service_arg is None:
        service_arg = []
    elif isinstance(service_arg, str):
        service_arg = service_arg.split(",")
    else:
        service_arg = list(flatten([_.split(",") for _ in service_arg]))

    service_arg = [_.strip("/") for _ in service_arg] if service_arg else ([str(default)] if default else [])

    # NOT elif because you can pass -s "minimal" -s "celeries" for example
    if "all" in service_arg:
        service_arg.remove("all")
        service_arg.extend(config.all_services)
    if "minimal" in service_arg:
        service_arg.remove("minimal")
        service_arg.extend(config.services_minimal)
    if "logs" in service_arg:
        service_arg.remove("logs")
        service_arg.extend(config.services_log)
    if "celeries" in service_arg:
        service_arg.remove("celeries")
        service_arg.extend(config.celeries)
    if "db" in service_arg and config.services_db:
        service_arg.remove("db")
        service_arg.extend(config.services_db)

    # service_arg is specified, filter through all available services:

    for service in service_arg:
        selected.update(fnmatch.filter(config.all_services, service))

    if service_arg and not selected:
        # when no service matches the name, don't return an empty list, as that would `up` all services
        # instead of the wanted list. This includes typos, where a single typo could cause all services to be started.
        cprint(f"ERROR: No services found matching: {service_arg!r}", color="red")
        exit(1)

    return list(selected)


def calculate_schema_hash(quiet: bool = False) -> str:
    """
    Calculates the sha1 digest of the files in the shared_code folder.

    When anything is changed, it will have a different hash, so migrate will be triggered.
    """
    filenames = sorted(Path("./shared_code").glob("**/*"))
    # ignore those pesky __pycache__ folders
    filenames = [_ for _ in filenames if "__pycache__" not in str(_) and _.is_file()]
    hasher = hashlib.sha256(b"")
    for filename in filenames:
        hasher.update(filename.read_bytes())

    if not quiet:
        print("schema hash: ", hasher.hexdigest())
    return hasher.hexdigest()


def task_for_namespace(ctx: Context, namespace: str, task_name: str) -> Task | None:
    """
    Get a task by namespace + task_name.

    Example:
        namespace: local, task_name: setup
    """

    if ns := ewok.find_namespace(ctx, namespace):
        return typing.cast(Task, ns.tasks.get(task_name))

    return None


def task_for_identifier(ctx: Context, identifier: str) -> Task | None:
    collection = ewok.tasks(ctx)

    return collection.tasks.get(identifier)


def get_task(ctx: Context, identifier: str = "") -> Task | None:
    """
    Get a task by the identifier you would use in the terminal.

    Example:
        local.setup
    """
    if not identifier:
        stack = traceback.extract_stack(limit=2)
        cprint(
            "WARN: get_task(identifier) is deprecated in favor of get_task(invoke.Context, identifier)",
            color="yellow",
        )
        format_frame(stack[0])
        return None

    if "." in identifier:
        return task_for_namespace(ctx, *identifier.split("."))
    else:
        return task_for_identifier(ctx, identifier)


_dotenv_settings: dict[str, dict[str, str]] = {}


def _apply_env_vars_to_template(source_lines: list[str], env: dict[str, str]) -> list[str]:
    needle = re.compile(r"# *template:")

    new_lines = []
    for line in source_lines:
        if not needle.findall(line):
            # nothing found, try next line
            new_lines.append(line)
            continue

        # split on template definition:
        old, template = needle.split(line)
        template = template.strip()
        # save the indention part, add an addition if no indention was found
        indention = (re.findall(r"^\s*", old) + [""])[0]  # noqa: RUF005 would make this complex
        if not old.lstrip().startswith("#"):
            # skip comment only lines
            new = template.format(**env)
            # reconstruct the line for the yaml file
            line = f"{indention}{new} # template: {template}"
        new_lines.append(line)
    return new_lines


# used for treafik config
def apply_dotenv_vars_to_yaml_templates(yaml_path: Path, dotenv_path: Path = DEFAULT_DOTENV_PATH) -> None:
    """Indention preserving templating of yaml files, uses dotenv_path for variables.

    Pythong formatting is used with a dictionary of environment variables used from os environment variables
    updated by the dotenv_path parsed .dotenv entries.
    Templating is found using `# template:`
    indention is saved, everything after the above indicator is python string formatted and written back.

    Example:
        |config:
        |    email: some@one.com # template: {EMAIL}

    assuming dotenv file contains:
        |EMAIL=yep@thatsme.com

    applying this function will result in:
        |config:
        |    email: yep@thatsme.com # template: {EMAIL}
    """
    env = os.environ.copy()
    env |= read_dotenv(dotenv_path)
    # env_variable_re = re.compile(r'\$[A-Z0-9]')
    with yaml_path.open(mode="r+") as yaml_file:
        source_lines = yaml_file.read().split("\n")
        new_lines = _apply_env_vars_to_template(source_lines, env)
        # move filepointer to the start of the file
        yaml_file.seek(0, FILE_START)
        # write all lines and newlines to the file
        yaml_file.write("\n".join(new_lines))
        # and remove any part that might be left over (when the new file is shorter than the old one)
        yaml_file.truncate()


# Singleton but depending on 'fname' (toml file name) and 'dotenv_path'
tomlconfig_singletons: dict[tuple[str, str], "TomlConfig"] = {}


def throw(error: Exception) -> Never:
    """
    Functional raise, useful for if ... else ... or callbacks.
    """
    raise error


class ServicesTomlConfig(typing.TypedDict, total=False):
    """
    [services] section of .toml
    """

    services: typing.Literal["discover"] | list[str]
    minimal: list[str]
    include_celeries_in_minimal: str  # 'true'/'1' or 'false'/'0'
    log: list[str]
    db: list[str]


# todo: keyof<ServicesTomlConfig> or something?
TomlKeys = typing.Literal["services", "minimal", "include_celeries_in_minimal", "log", "db"]


class ConfigTomlDict(typing.TypedDict, total=True):
    """
    Data from .toml
    """

    services: ServicesTomlConfig
    dotenv: AnyDict


def boolish(value: typing.Literal["y", "yes", "t", "true", "1", "n", "no", "false", "f", "0"] | str | int) -> bool:
    """
    Convert a given value to a boolean.

    Args:
        value (Union[str, int]): The value to be converted.
            Accepts strings representing true/false values such as "y", "yes", "t", "true", "1" for true
            and "n", "no", "false", "f", "0" for false, as well as integers.

    Returns:
        bool: The boolean representation of the input value.
    """
    return bool(value) and str(value)[0].strip().lower() in {"y", "t", "1"}


@dataclass
class TomlConfig:
    config: ConfigTomlDict
    all_services: list[str]
    celeries: list[str]
    services_minimal: list[str]
    services_log: list[str]
    services_db: list[str]
    services_health: list[str]

    dotenv_path: Path

    # __loaded was replaced with tomlconfig_singletons

    @classmethod
    def load(
        cls,
        fname: str | Path = DEFAULT_TOML_NAME,
        dotenv_path: Optional[Path] = None,
        cache: bool = True,
    ) -> "TomlConfig | None":
        """
        Load config toml file, raising an error if it does not exist.

        Since this file should be in .git error suppression is not needed.
        Returns a dictionary with CONFIG, ALL_SERVICES, CELERIES and MINIMAL_SERVICES
        """
        singleton_key = (str(fname), str(dotenv_path))
        ctx = Context()

        if cache and (instance := tomlconfig_singletons.get(singleton_key)):
            return instance

        config_path = Path(fname)  # probably config.toml
        dc_path = Path("docker-compose.yml")

        if not dc_path.exists():
            cprint(
                "docker-compose.yml file is missing, toml config could not be loaded. Functionality may be limited.",
                color="yellow",
            )
            return None

        if not config_path.exists():
            setup(ctx)

        config = read_toml_config(config_path)
        # todo: if setup runs, reload config

        if "services" not in config:
            setup(ctx)
            config = read_toml_config(config_path)

        for toml_key in [
            "minimal",
            "services",
            "include_celeries_in_minimal",
            "log",
            "db",
        ]:
            if toml_key not in config["services"]:
                setup(ctx)
            config = read_toml_config(config_path)

        if config["services"].get("services", "discover") == "discover":
            compose = load_dockercompose_with_includes(dc_path=dc_path)

            all_services = list(compose["services"].keys())
        else:
            all_services = typing.cast(list[str], config["services"]["services"])

        celeries = [s for s in all_services if "celery" in s.lower()]

        minimal_services = config["services"]["minimal"]
        if boolish(config["services"].get("include_celeries_in_minimal", "false")):
            minimal_services += celeries

        tomlconfig_singletons[singleton_key] = instance = TomlConfig(
            config=config,
            all_services=all_services,
            celeries=celeries,
            services_minimal=minimal_services,
            services_log=config["services"]["log"],
            services_db=config["services"]["db"],
            services_health=config["services"].get("health", []),
            dotenv_path=Path(config.get("dotenv", {}).get("path", dotenv_path or DEFAULT_DOTENV_PATH)),
        )
        return instance


def process_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values = dotenv_values(env_path)
    return dict(values)


def exists_nonempty(path: Path) -> bool:
    """
    Checks whether a given file path exists and is non-empty.

    This function determines if the specified path represents an existing
    file and whether it contains any data (i.e., its size is greater than 0).

    Args:
        path (Path): A Path object representing the file path to check.

    Returns:
        bool: True if the file exists and is non-empty, otherwise False.
    """
    return path.exists() and path.stat().st_size > 0


def read_dotenv(env_path: Path = DEFAULT_DOTENV_PATH) -> dict[str, str]:
    """
    Read .env file from env_path and return a dict of key/value pairs.

    If the .env file doesn't exist at env_path, traverse up the directory tree
    looking for one, stopping when a docker-compose.* file is found (project root).

    :param env_path: optional path to .env file
    :return: dict of key/value pairs from the .env file
    """
    if not env_path:
        # for backwards compatibility, if None is passed: still use the default.
        env_path = DEFAULT_DOTENV_PATH

    cache_key = str(env_path) if env_path else "."
    if existing := _dotenv_settings.get(cache_key):
        # 'cache'
        return existing

    # First try the exact path provided
    if exists_nonempty(env_path):
        items = process_env_file(env_path)
        _dotenv_settings[cache_key] = items
        return items

    # If not found and it's the default name, traverse up the tree
    if env_path.name == DEFAULT_DOTENV_PATH.name:
        current_dir = Path.cwd()

        while current_dir != current_dir.parent:  # Stop at filesystem root
            # Look for .env in current directory
            potential_env = current_dir / DEFAULT_DOTENV_PATH.name
            if exists_nonempty(potential_env):
                items = process_env_file(potential_env)
                _dotenv_settings[cache_key] = items
                return items

            # Check if we've reached a project root (docker-compose file exists)
            if any(current_dir.glob("docker-compose.*")):
                # Found project root, stop searching if we're not in the original directory
                if current_dir != Path.cwd():
                    break
            # Move up one directory
            current_dir = current_dir.parent

    # If still not found, return empty dict (existing behavior)
    items = {}
    _dotenv_settings[cache_key] = items
    return items


# noinspection PyDefaultArgument
def warn_once(
    warning: str,
    previously_shown: list[str] = [],
    color: Optional[Color] = None,
    **print_kwargs: typing.Any,
) -> None:
    """
    Mutable default 'previously_shown' is there on purpose, to track which warnings were already shown!
    """
    if warning in previously_shown:
        # already seen
        return

    previously_shown.append(warning)

    cprint(
        warning,
        color=color,
        **print_kwargs,
    )


type DefaultFn = typing.Callable[[], Optional[str]]


def check_env(
    key: str,
    default: Optional[str] | DefaultFn,
    comment: str,
    # optionals:
    prefix: Optional[str] = None,
    suffix: Optional[str] = None,
    # note: 'postfix' should be 'suffix' but to be backwards compatible we can't just remove it!
    postfix: Optional[str] = None,
    # different config paths:
    env_path: Optional[str | Path] = None,
    force_default: Optional[bool] = False,
    allowed_values: typing.Iterable[str] = (),
    toml_path: None = None,
) -> str:
    """
    Test if key is in .env file path, appends prompted or default value if missing.

    Args:
        key: The environment variable key to check.
        default: The default value to use if the key is not found. Can also be a function for lazy evaluation.
        comment: A comment describing the purpose of the environment variable.
        prefix: An optional prefix to prepend to the key.
        suffix: An optional suffix to append to the key.
        postfix: An optional parameter for backward compatibility with 'suffix'.
        env_path: An optional path to the environment file.
        force_default: Whether to force the default value even if the key exists.
        allowed_values: A list of allowed values for the environment variable.
        toml_path: Optional path to a TOML configuration file.

    Returns:
        The value of the environment variable, either from the file, default, or forced.


    Example:
        > check_env(
        >    key="SOME_KEY",
        >    default=lambda c: slow_function()
        >    comment="This key has a lazily evaluated default",
        >    ...
        > )
    """
    if toml_path:
        warn_once(f"Deprecated: toml_path ({toml_path} is not used by check_env anymore.)", color="yellow")

    env_path = Path(env_path or DEFAULT_DOTENV_PATH)
    if not env_path.exists():
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.touch()

    # config = TomlConfig.load(toml_path, env_path)
    env = read_dotenv(env_path)

    if key in env:
        return env[key]

    if suffix and postfix:
        warnings.warn(
            "! both a 'suffix' and a 'postfix' parameter were specified, "
            "but only 'suffix' will be used since 'postfix' is just an alias!",
            category=DeprecationWarning,
        )
    elif postfix:
        warnings.warn(
            "The 'postfix' option has been replaced by 'suffix' and may be removed in the future.",
            category=DeprecationWarning,
        )

    suffix = suffix or postfix

    if callable(default):
        default = default()

    if force_default:
        value = default or ""
    else:
        response = input(f"Enter value for {key} ({comment})\n default=`{default}`: ")
        value = response.strip() or default or ""

        if allowed_values and value not in allowed_values:
            raise ValueError(f"Invalid value '{response}'. Please choose one of {allowed_values}")

    if prefix:
        value = prefix + value
    if suffix:
        value += suffix

    with env_path.open(mode="a") as env_file:
        # append mode ensures we're writing at the end
        env_file.write(f"\n{key.upper()}={value}")

        # update in memory too:
        env[key] = value
        return value


def get_env_value(key: str, default: str | type[Exception] = KeyError) -> str:
    """
    Get a specific env value by name.
    If no default is given and the key is not found, a KeyError is raised.
    """
    env = read_dotenv()
    if key in env:
        return env[key]
    elif isinstance(default, type) and issubclass(default, Exception):
        raise default(key)

    return default


def set_env_value(path: Path, target: str, value: str | None) -> None:
    """
    Update/set environment variables in the .env file, keeping comments intact.

    set_env_value(Path('.env'), 'SCHEMA_VERSION', schemaversion)

    Args:
        path: pathlib.Path designating the .env file
        target: key to write, probably best to use UPPERCASE
        value: string value to write (or anything that converts to a string using str()).
               If None, the key will be removed from the file (if present) and not added.
    """
    path.touch(exist_ok=True)

    with path.open(mode="r") as env_file:
        # open the .env file and read every line in the inlines
        inlines = env_file.read().split("\n")

    outlines = []  # lines for output
    geschreven = False
    for line in inlines:
        if line.strip().startswith("#"):
            # ignore comments
            outlines.append(line)
            continue
        # remove redundant whitespace
        line = line.strip()
        if not line:
            # remove empty lines
            continue
        # convert to tuples
        key, oldvalue = line.split("=", 1)
        # clean the key and value
        key = key.strip()
        if key == target:
            if value is None:
                # Remove this key by not adding it to outlines
                geschreven = True
                continue
            # add the new tuple to the lines
            outlines.append(f"{key}={value}")
            geschreven = True
        else:
            # or leave it as it is
            outlines.append(line)

    if not geschreven and value is not None:
        outlines.append(f"{target.strip().upper()}={value.strip()}")

    with path.open(mode="w") as env_file:
        env_file.write("\n".join(outlines))
        env_file.write("\n")


def write_content_to_toml_file(
    content_key: TomlKeys,
    content: str | list[str] | None,
    filename: str | Path = DEFAULT_TOML_NAME,
    allow_empty: bool = False,
) -> None:
    if not (content or allow_empty):
        return

    filepath = Path(filename)

    config_toml_file = read_toml_config(filepath)
    config_toml_file["services"][content_key] = content

    write_toml_config(filepath, config_toml_file)


def get_content_from_toml_file(
    services: list[str],
    toml_contents: ConfigTomlDict,
    content_key: TomlKeys,
    content: str,
    default: list[str] | str,
    overwrite: bool = False,
    allow_empty: bool = False,
) -> list[str] | str | None:
    """
        Gets content from a TOML file.
    feat/ew_setup_2084/gwen
        :param services: A list of services.
        :param toml_contents: A dictionary representing the TOML file.
        :param content_key: The key to look for in the TOML file.
        :param content: The content to display to the user.
        :param default: The default value to return if the conditions are not met.
        :param overwrite: don't skip if key already exists
        :param allow_empty: add an option to the dropdown to select no containers (e.g. for a service without database)

        :return: The content from the TOML file or the default value.
        :rtype: Any
    """

    has_existing_value = "services" in toml_contents and content_key in toml_contents["services"]

    if has_existing_value and not overwrite:
        print("skipping", content_key)
        return ""

    selected: set[str] = set()
    if has_existing_value:
        selected.update(toml_contents["services"][content_key])
    elif default:
        selected.update(default)

    selection = interactive_selected_checkbox_values(services, content, selected=selected, allow_empty=allow_empty)
    if allow_empty and selection is None:
        return None

    return selection or default


def setup_config_file(filename: str | Path = DEFAULT_TOML_NAME) -> None:
    """
    sets up config.toml for use
    """
    filepath = Path(filename)

    config_toml_file = tomlkit.loads(filepath.read_text())
    if "services" not in config_toml_file:
        filepath.write_text("\n[services]\n")


def read_toml_config(fp: Path) -> ConfigTomlDict:
    """
    Read the config at filepath, and cast to the right typeddict.
    """
    config_toml_file = tomlkit.loads(fp.read_text())

    return typing.cast(ConfigTomlDict, config_toml_file)


def write_toml_config(fp: Path, config: ConfigTomlDict) -> int:
    return fp.write_text(tomlkit.dumps(config))


def write_user_input_to_config_toml(
    all_services: list[str],
    filename: str | Path = DEFAULT_TOML_NAME,
    overwrite: bool = False,
) -> TomlConfig | None:
    """
    write chosen user dockers to config.toml

    :param all_services: list of all docker services that are in the docker-compose.yml
    :param filename: which toml file to write to (default = .toml)
    :param overwrite: by default, skip keys that already have a value
    :return:
    """
    filepath = Path(filename)
    services_no_celery = [service for service in all_services if "celery" not in service]
    services_celery = [service for service in all_services if "celery" in service]

    setup_config_file()
    # services
    services_list = "discover"
    write_content_to_toml_file("services", services_list)

    config_toml_file = read_toml_config(filepath)

    # get chosen services for minimal and logs
    minimal_services = typing.cast(  # type: ignore
        list[str],
        (
            services_no_celery
            if config_toml_file["services"]["services"] == "discover"
            else config_toml_file["services"]["services"]
        ),
    )

    # services
    content = get_content_from_toml_file(
        minimal_services,
        config_toml_file,
        "minimal",
        "select minimal services you want to run on `ew up`: ",
        [],
        overwrite=overwrite,
    )
    write_content_to_toml_file("minimal", content, filename)

    # check if minimal and celeries exist, if so add celeries to services
    if not services_celery:
        write_content_to_toml_file("include_celeries_in_minimal", "false")
    elif services_celery and (
        "services" not in config_toml_file
        or "include_celeries_in_minimal" not in config_toml_file["services"]
        or overwrite
    ):
        # check if user wants to include celeries
        include_celeries = (
            "true" if confirm("do you want to include celeries in minimal [Yn]: ", default=True) else "false"
        )
        write_content_to_toml_file("include_celeries_in_minimal", include_celeries)

    content = get_content_from_toml_file(
        minimal_services,
        config_toml_file,
        "log",
        "select services to be logged: ",
        [],
        overwrite=overwrite,
    )
    write_content_to_toml_file("log", content, filename)

    # db

    possibly_postgres = [_ for _ in minimal_services if "pg" in _]

    content = get_content_from_toml_file(
        minimal_services,
        config_toml_file,
        "db",
        "select database containers: ",
        possibly_postgres,
        overwrite=overwrite,
        allow_empty=True,
    )

    write_content_to_toml_file("db", content or [], filename, allow_empty=content is None)

    return TomlConfig.load(filename, cache=False)


def load_dockercompose_with_includes(
    c: Optional[Context] = None,
    dc_path: str | Path = "docker-compose.yml",
) -> AnyDict:
    """
    Since we're using `docker compose` with includes, simply yaml loading docker-compose.yml is not enough anymore.

    This function uses the `docker compose config` command to properly load the entire config with all enabled services.
    """
    if not c:
        c = Context()
    if not isinstance(dc_path, Path):
        dc_path = Path(dc_path)

    if not dc_path.exists():
        raise FileNotFoundError(dc_path)

    if ran := c.run(f"{DOCKER_COMPOSE} -f {dc_path} config", hide=True):
        processed_config = ran.stdout.strip()
        # mimic a file to load the yaml from
        fake_file = io.StringIO(processed_config)
        return typing.cast(AnyDict, yaml.safe_load(fake_file))
    else:
        return {}


def prompt_validate_sudo_pass(c: Context):
    sudo_pass = getpass("Please enter the sudo password: ")
    c.config.sudo.password = sudo_pass

    try:
        result = c.sudo("echo ''", warn=True, hide=True)
        if not (result and result.ok):
            raise invoke.exceptions.AuthFailure(result, "sudo")

        cprint("Sudo password accepted!", color="green", file=sys.stderr)
        return sudo_pass
    except invoke.exceptions.AuthFailure as e:
        cprint(str(e), color="red", file=sys.stderr)
        return None


@task()
def require_sudo(c: Context) -> bool:
    """
    Can be used as a 'pre' hook for invoke tasks to make sure sudo is ready to be used,
    without prompting for a password later on (which could fail due to not passing data to stdin on a remote host).

    Usage:
        @task(pre=[require_sudo])
        def setup(c): ...

        # or, if you're not in a @task but you do have access to c (Context), e.g. in a helper function:
        def my_func(c):
            if require_sudo(c):
                c.sudo('echo "I am the captain now."')

    """
    ran = c.run("sudo --non-interactive echo ''", warn=True, hide=True)
    if ran and ran.ok:
        # prima
        return True

    with contextlib.suppress(Exception):
        if current := keyring.get_password("edwh", "sudo"):
            c.config.sudo.password = current
            return True

    if prompt_validate_sudo_pass(c):
        return True
    else:
        cprint("Stopping now.")
        exit(1)


def build_toml(c: Context, overwrite: bool = False) -> TomlConfig | None:
    try:
        docker_compose = load_dockercompose_with_includes(c)
    except FileNotFoundError:
        cprint("docker-compose.yml file is missing, setup could not be completed!", color="red")
        return None

    services: AnyDict = docker_compose["services"]
    return write_user_input_to_config_toml(list(services.keys()), overwrite=overwrite)


@task()
def sudo(c: Context):
    # 1.
    # check current status in keyring
    try:
        current = keyring.get_password("edwh", "sudo")
    except Exception:
        current = None

    # 2. change text based on current status (re-authorize)
    if current:
        allow = confirm(
            "Would you like to re-authorize edwh to run sudo commands without password entry? [Yn]",
            default=True,
        )
    else:
        allow = confirm(
            "Would you like to authorize edwh to run sudo commands without password entry? [yN]",
            default=False,
        )

    if allow:
        # if yes: add to keyring
        if sudo_pass := prompt_validate_sudo_pass(c):
            keyring.set_password("edwh", "sudo", sudo_pass)
        else:
            exit(1)

    else:
        # else: remove from keyring
        keyring.delete_password("edwh", "sudo")


@task(
    pre=[require_sudo],
    help={
        "new_config_toml": "will REMOVE and create a new config.toml file",
    },
    hookable=True,
)
def setup(c: Context, new_config_toml: bool = False, _retry: bool = False) -> dict:
    """
    sets up config.toml and tries to run setup in local tasks.py if it exists

    while configuring the config.toml the program will ask you to select a service by id.
    All service can be found by the print that is done above.
    While giving up id's please only give 1 id at the time, this goes for the services and the minimal services

    """
    config_toml = Path(DEFAULT_TOML_NAME)
    dc_path = Path("docker-compose.yml")

    if (
        new_config_toml
        and config_toml.exists()
        and confirm(
            colored(f"Are you sure you want to remove the {DEFAULT_TOML_NAME}? [yN]", "red"),
            default=False,
        )
    ):
        config_toml.unlink()

    copy_fallback_toml(force=False)  # only if .toml is missing, try to copy default.toml

    if dc_path.exists():
        print("getting services...")

        try:
            # run `docker compose config` to build a yaml with all processing done, include statements included.
            build_toml(c)
        except Exception as e:
            cprint(
                f"Something went wrong trying to create a {DEFAULT_TOML_NAME} from docker-compose.yml ({e})",
                color="red",
            )
            # this could be because 'include' requires a variable that's setup in local task, so still run that:
    else:
        cprint("docker-compose file is missing, setup might not be completed properly!", color="yellow")

    # local/plugin setup happens here because of `hookable`
    return {}


@task()
def search_adjacent_setting(c: Context, key: str, silent: bool = False) -> AnyDict:
    """
    Search for key in all ../*/.env files.
    """
    key = key.upper()
    if not silent:
        print("search for ", key)
    envs = (pathlib.Path(c.cwd) / "..").glob("*/.env")
    adjacent_settings = {}
    for env_path in envs:
        value = read_dotenv(env_path).get(key)
        project = env_path.parent.name
        if not silent:
            print(f"{project:>20} : {value}")
        adjacent_settings[project] = value
    return adjacent_settings


def next_value(c: Context, key: list[str] | str, lowest: int, silent: bool = True) -> int:
    """Find all other project settings using key, adding 1 to max of all values, or defaults to lowest.

    next_value(c, 'REDIS_PORT', 6379) -> might result 6379, or 6381 if this is the third project to be initialised
    next_value(c, ['PGPOOL_PORT','POSTGRES_PORT','PGBOUNCER_PORT'], 5432) -> finds the next port searching for all keys.
    """
    keys = [key] if isinstance(key, str) else key
    all_settings: AnyDict = {}
    for key in keys:
        settings = search_adjacent_setting(c, key, silent)
        all_settings |= {f"{k}/{key}": v for k, v in settings.items() if v}
        if not silent:
            print()
    values = {int(v) for v in all_settings.values() if v}
    return max(values) + 1 if any(values) else lowest


THREE_WEEKS = 60 * 24 * 7 * 3


@task()
def clean_old_sessions(c: Context, relative_glob: str = "web2py/apps/*/sessions", minutes: int = THREE_WEEKS) -> None:
    for directory in Path.cwd().glob(relative_glob):
        c.sudo(f'find "{directory}" -type f -mmin +{minutes} -exec rm -f "{{}}" +;')
        remove_empty_dirs(c, directory)


@task()
def remove_empty_dirs(c: Context, path: str | Path) -> None:
    c.sudo(f'find "{path}" -type d -exec rmdir --ignore-fail-on-non-empty {{}} +')


def set_permissions(
    c: Context,
    path: str,
    uid: int = 1050,
    gid: int = 1050,
    filepermissions: int = 664,
    directorypermissions: int = 775,
) -> None:
    """
    Set all directories in path to 'directorypermissions',
        all files to 'filepermissions'
        and chown the right user+group.
    """
    # sudo(f'find "{path}" -type d -print0 | sudo xargs --no-run-if-empty -0 chmod {directorypermissions}')
    c.sudo(f'find "{path}" -type d -exec chmod {directorypermissions} {{}} +')
    # find all files, print the output, feed those to xargs which converts lines in to arguments to the chmod command.
    # sudo(f'find "{path}" -type f -print0 | sudo xargs --no-run-if-empty -0 chmod {filepermissions}')
    c.sudo(f'find "{path}" -type f -exec chmod {filepermissions} {{}} +')
    # simply apply new ownership to each and every directory
    c.sudo(f'chown -R {uid}:{gid} "{path}" ')


@task(help=dict(silent="do not echo the password"))
def generate_password(_: Context, silent: bool = False, dice: int = 6) -> str:
    """
    Generate a diceware password using --dice 6.

    Arggs:
        _: invoke Context
        silent: don't print the generated password?
        dice: amount of words to generate

    """
    return _generate_password(silent=silent, dice=dice)


def fuzzy_match(val1: str, val2: str, verbose: bool = False) -> float:
    """
    Get the similarity score between two values.

    Used by `edwh settings -f ...` when no exact match was found.
    """
    similarity = fuzz.partial_ratio(val1, val2)
    if verbose:
        print(f"similarity of {val1} and {val2} is {similarity}", file=sys.stderr)
    return similarity


def _settings(find: typing.Optional[str], fuzz_threshold: int = 75) -> typing.Iterable[tuple[str, typing.Any]]:
    all_settings = read_dotenv().items()
    if find is None:
        # don't loop
        return all_settings
    else:
        find = find.upper()
        # if nothing found exactly, try again but fuzzy (could be slower)
        exact_match = [(k, v) for k, v in all_settings if find in k.upper() or find in v.upper()]
        return exact_match or [(k, v) for k, v in all_settings if fuzzy_match(k.upper(), find) > fuzz_threshold]


# noinspection PyUnusedLocal
@task(
    help=dict(find="search for this specific setting", as_json="output as json dictionary"),
    flags={
        "as_json": ("j", "json", "as-json"),
        "fuzz_threshold": ("t", "fuzz-threshold"),
    },
)
def settings(_: Context, find: Optional[str] = None, fuzz_threshold: int = 75, as_json: bool = False) -> None:
    """
    Show all settings in .env file or search for a specific setting using -f/--find.
    """
    rows = _settings(find, fuzz_threshold)
    if as_json:
        print(json.dumps(dict(rows), indent=3))
    else:
        print(tabulate.tabulate(rows, headers=["Setting", "Value"]))


def show_related_settings(ctx: Context, services: list[str]) -> None:
    config = dc_config(ctx)

    rows: AnyDict = {}
    for service in services:
        if service_settings := _settings(service):
            rows |= service_settings
        else:
            with contextlib.suppress(TypeError, KeyError):
                rows |= config["services"][service]["environment"]

    print(tabulate.tabulate(rows.items(), headers=["Setting", "Value"]))


@task(aliases=("volume",))
def volumes(ctx: Context) -> None:
    """
    Show container and volume names.

    Based on `docker-compose ps -q` ids and `docker inspect` output.
    """
    lines: list[AnyDict] = []
    ran = ctx.run(f"{DOCKER_COMPOSE} ps -q", hide=True, warn=True)
    stdout = ran.stdout if ran else ""
    for container_id in stdout.strip().split("\n"):
        with contextlib.suppress(EnvironmentError):
            info = docker_inspect(ctx, container_id)[0]
            container = info["Name"]
            lines.extend(
                dict(container=container, volume=volume)
                for volume in [_["Name"] for _ in info["Mounts"] if _["Type"] == "volume"]
            )

    print(tabulate.tabulate(lines, headers="keys"))


def check_paused(ctx: Context, service: str) -> bool:
    """Check if a service container is paused."""
    result = ctx.run(f"{DOCKER_COMPOSE} ps --format json {service}", hide=True, warn=True)
    try:
        container_info = json.loads(result.stdout.strip())
        if isinstance(container_info, list):
            container_info = container_info[0] if container_info else {}

        state = container_info.get("State", "")
        return state == "paused"
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        return False


def get_service_dependencies(ctx: Context, service: str) -> list[str]:
    """Get the dependencies (depends_on) for a service from docker-compose config."""
    result = ctx.run(f"{DOCKER_COMPOSE} config --format json", hide=True, warn=True)
    try:
        config = json.loads(result.stdout.strip())
        services = config.get("services", {})
        service_config = services.get(service, {})
        depends_on = service_config.get("depends_on", {})

        # depends_on can be a list or a dict
        if isinstance(depends_on, dict):
            return list(depends_on.keys())
        elif isinstance(depends_on, list):
            return depends_on
        return []
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Could not get dependencies for {service}: {e}")
        return []


def get_paused_services_with_deps(ctx: Context, services: list[str]) -> list[str]:
    """Get all paused services including their dependencies.

    Args:
        ctx: Invoke context
        services: List of service names to check

    Returns:
        List of paused service names (including dependencies)
    """
    # Collect all services including dependencies
    all_services = set(services)
    for service in services:
        dependencies = get_service_dependencies(ctx, service)
        all_services.update(dependencies)

    # Check which services are paused
    return [svc for svc in all_services if check_paused(ctx, svc)]


# noinspection PyShadowingNames


@task(
    help=dict(
        service="Service to up, defaults to .toml's [services].minimal. Can be used multiple times, handles wildcards.",
        build="request a build be performed first",
        quickest="restart only, no down;up",
        stop_timeout="timeout for stopping services, defaults to 2 seconds",
        tail="tails the log of restart services, defaults to False",
        clean="adds `--renew-anon-volumes --build` to `docker-compose up` command ",
    ),
    iterable=["service"],
    flags={
        "tail": ("tail", "logs", "l"),  # instead of -a; NOTE: 'tail' must be first (matches parameter name)
    },
    hookable=True,
)
def up(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    build: bool = True,
    quickest: bool = False,
    stop_timeout: int = 2,
    tail: bool = False,
    clean: bool = False,
    show_settings: bool = True,
    wait: bool = False,
) -> dict:
    """Restart (or down;up) some or all services, after an optional rebuild."""
    config = TomlConfig.load()
    # recalculate the hash and save it, so with the next up, migrate will see differences and start migration
    set_env_value(DEFAULT_DOTENV_PATH, "SCHEMA_VERSION", calculate_schema_hash())
    # test for --service arguments, if none given: use defaults
    services = service_names(service or (config.services_minimal if config else []))
    services_ls = " ".join(services)

    # Check for paused containers and unpause them
    if paused_services := get_paused_services_with_deps(ctx, services):
        paused_ls = " ".join(paused_services)
        cprint(f"Unpausing and stopping services: {paused_ls}", "blue")
        ctx.run(f"{DOCKER_COMPOSE} unpause {paused_ls}", pty=True)
        # unpaused containers often get unhealthy so also stop them:
        ctx.run(f"{DOCKER_COMPOSE} stop {paused_ls}", pty=True)

    if quickest:
        ctx.run(f"{DOCKER_COMPOSE} restart {services_ls}")
    else:
        ctx.run(f"{DOCKER_COMPOSE} stop -t {stop_timeout}  {services_ls}")
        # note: checking if build is required due to outdated versions seems undoable, docker has no api for it
        #       so we're just adding --build. There also is no --pull, so you need to run ew build or dc pull manually

        ctx.run(
            f"{DOCKER_COMPOSE} up "
            f"{'--renew-anon-volumes' if clean else ''} "
            f"{'--build' if build else ''} "
            f"-d {services_ls}",
            pty=True,
        )

    if show_settings:
        show_related_settings(ctx, services)
    if tail:
        ctx.run(f"{DOCKER_COMPOSE} logs --tail=10 -f {services_ls}")
    if wait:
        health(ctx, services, wait=True)

    # local/plugin up happens here because of `hookable`
    return {
        "services": services,
    }


@task()
def inspect_health(ctx, container: str, quiet: bool = False) -> dict:
    tab = " " * 2
    result = {}

    with contextlib.suppress(OSError):
        container_ids = find_container_ids(ctx, container) or [container]

        for container_id in container_ids:
            result[container_id] = docker_inspect(ctx, container_id, '--format "{{json .State.Health }}"')

    if result and not quiet:
        print(tab + yaml.dump(result, allow_unicode=True).replace("\n", f"\n{tab}"))

    return result


@task(
    iterable=("service",),
)
def wait_until_healthy(ctx: Context, services: list[str] = (), quiet: bool = False):
    initial_length = 0
    # for every container with a health check, wait for it to be either healthy or dead (not starting)
    while missing := [_.container for _ in get_healths(ctx, *services) if _ and _.health == "starting"]:
        if not quiet:
            msg = f" Waiting for {missing}" + " " * 25
            if not initial_length:
                initial_length = len(msg)

            print(msg, end="\r")

    # wait is done, now print empty line to cleanup print traces:
    if initial_length and not quiet:
        print(" " * initial_length)

    return 0


@task(
    flags={
        "show_all": ("all", "a"),
    },
    iterable=("service",),
)
def health(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    wait: bool = False,
    show_all: bool = False,
    quiet: bool = False,
    verbose: bool = False,
) -> int:
    """
    Show health status for docker containers

    Args:
        ctx: invoke context
        service: which services to show logs for.
            If you have a 'health' section in your .toml, those services will be used by default.
            Otherwise, 'all' will be used by default.
        wait: should the command wait until all services are healthy? Defaults to only showing status once and exiting.
        show_all: show all services. Alias for `-s all`
        quiet: don't print anything, only return amount of unhealthy containers
        verbose: print health inspection for unhealthy containers

    Returns:
        Number of unhealthy services (0 is good, just like bash exit codes).
            Should always be 0 if you use --wait
    """
    config = TomlConfig.load()
    # test for --service arguments, if none given: use defaults
    if show_all:
        services = service_names("all")
    elif service:
        services = service_names(service)
    elif config:
        services = service_names(config.services_health or config.all_services)
    else:
        services = []

    if wait:
        return wait_until_healthy(ctx, services, quiet=quiet)

    healths = get_healths(ctx, *services)
    if not quiet:
        for health_status in sorted((_ for _ in healths if _ is not None), key=lambda h: (h.level, h.container)):
            print(f"- {health_status}")
            if verbose and not health_status.ok and health_status.container_id:
                inspect_health(ctx, health_status.container_id)

    # return amount of sick containers:
    return sum(not _.ok for _ in healths)


@task(aliases=("psa",))
def ps_all(ctx):
    """
    Show Docker Compose projects with container counts and summarized status.
    """
    result = ctx.run("docker ps --format '{{json .}}'", hide=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]

    projects = defaultdict(lambda: {"count": 0, "container_statuses": []})

    for line in lines:
        container_data = json.loads(line)
        container_name = container_data["Names"]
        container_state = container_data.get("State", "")
        container_status_text = container_data.get("Status", "").lower()

        project_name = container_name.split("-")[0]
        projects[project_name]["count"] += 1

        # Determine container status with priority: unhealthy > paused > healthy/ok > others
        if "unhealthy" in container_status_text or "health: starting" in container_status_text:
            container_status = "unhealthy"
        elif "paused" in container_state:
            container_status = "paused"
        elif "healthy" in container_status_text:
            container_status = "healthy"
        elif container_state == "running":
            container_status = "ok"
        else:
            container_status = container_state

        projects[project_name]["container_statuses"].append(container_status)

    table_rows = []
    for project_name, info in sorted(projects.items()):
        statuses_set = set(info["container_statuses"])

        if "unhealthy" in statuses_set:
            project_status = "unhealthy"
        elif "paused" in statuses_set:
            project_status = "paused"
        # The <= operator for sets checks if statuses_set is a subset of {"healthy", "ok"}
        # i.e., all containers are either healthy or ok
        elif statuses_set <= {"healthy", "ok"}:
            project_status = "ok"
        elif len(statuses_set) > 1:
            project_status = "mixed"
        else:
            project_status = list(statuses_set)[0]

        table_rows.append((project_name, info["count"], project_status))

    print(tabulate.tabulate(table_rows, headers=["Project", "Containers", "Status"], tablefmt="pipe"))


@task(
    iterable=["service", "columns"],
    help=dict(
        service="Service to query, can be used multiple times, handles wildcards.",
        quiet="Only show container ids. Useful for scripting.",
        columns="Which columns to display?",
        full="Don't truncate the command.",
    ),
    flags={
        "show_all": ("all", "a"),
    },
)
def ps(
    ctx: Context,
    quiet: bool = False,
    service: typing.Collection[str] | None = None,
    columns: typing.Collection[str] | None = None,
    full: bool = False,
    show_all: bool = False,
) -> None:
    """
    Show process status of services.
    """
    trunc_after = 30
    if not Path("docker-compose.yml").exists():
        cprint("You're not in a docker compose environment.", color="red")
        if confirm("Would you like to see all running environments? [Yn]", default=True):
            ps_all(ctx)
        return

    flags = []

    if show_all:
        flags.append("-a")
    if quiet:
        flags.append("-q")

    # we may trunc it ourselves:
    flags.append("--no-trunc")

    flags.extend(service_names(service or []))

    args_str = " ".join(flags)

    ran = ctx.run(
        f"{DOCKER_COMPOSE} ps --format json {args_str}",
        warn=True,
        hide=True,
    )
    ps_output = ran.stdout.strip() if ran else ""

    services = []

    # list because it's ordered
    selected_columns = list(columns or []) or ["Name", "Command", "Image", "State", "Health", "Ports"]

    for service_json in ps_output.split("\n"):
        if not service_json:
            # empty line
            continue

        service_dict = json.loads(service_json)
        service_dict = {k: v for k, v in service_dict.items() if k in selected_columns}
        if not full:
            service_dict["Command"] = shorten(service_dict["Command"], trunc_after)
            service_dict["Image"] = shorten(service_dict["Image"], trunc_after)

        service_dict = dict(sorted(service_dict.items(), key=lambda x: selected_columns.index(x[0])))
        services.append(service_dict)

    print(tabulate.tabulate(services, headers="keys"))


@task(
    help=dict(
        quiet="Only show ids (mostly directories). Useful for scripting.",
    ),
)
def ls(ctx: Context, quiet: bool = False) -> None:
    """
    List running compose projects.
    """
    ctx.run(f"{DOCKER_COMPOSE} ls {'-q' if quiet else ''}")


def get_docker_info(ctx: Context, services: list[str]) -> dict[str, AnyDict]:
    """
    Return a dict of {id: service}
    """
    # -aq doesn't keep the same order of services, so use json format to get ID with service name.
    # use --no-trunc to get full ID instead of short one
    if ran := ctx.run(f"{DOCKER_COMPOSE} ps --format json --no-trunc -a {' '.join(services)}", hide=True):
        rows = ran.stdout
    else:
        rows = ""

    result = {}

    for line in rows.split("\n"):
        if not line:
            continue

        # each line contains one json object
        info = json.loads(line)

        result[info["ID"]] = info

    return result


T_Stream = typing.Literal["stdout", "stderr", "out", "err", ""]


def follow_logs(
    ctx: Context,
    container_id: str,
    project: str,
    longest_name: int,
    color: ColorFn,
    since: str | None,
    verbose: bool,
    timestamps: bool,
    stream: T_Stream = "",
    filter_pattern: str = "",
    stop_event: threading.Event = None,
) -> bool:
    """
    Follows logs of a specified Docker container while optionally filtering and formatting output.

    This function actively monitors the logs of a given container, allowing for custom filtering
    through a regular expression pattern and handling streams like `stdout` or `stderr`. It is
    designed to handle specific options such as including timestamps or verbose prefixes, and it
    can restart the log retrieval process in case of certain interruptions.

    Parameters:
        ctx (Context): Execution context used to run commands.
        container_id (str): ID of the container whose logs are being followed.
        project (str): Project or prefix name associated with the container.
        longest_name (int): Length of the longest name used for alignment in output.
        color (ColorFn): Function to apply color formatting to output, typically the container name.
        since (str | None): Initial timestamp or date from which logs should be retrieved, if available.
        verbose (bool): Whether to include verbose prefixes (e.g., stream type) in output.
        timestamps (bool): Whether to include timestamps from the logs in the output.
        stream (Literal["stdout", "stderr", "out", "err", ""]): Stream type to handle in the output.
            An empty string ("") implies both streams will be followed.
        filter_pattern (str): Regular expression pattern used to filter log entries. Defaults to an
            empty string, meaning no filtering is applied.

    Returns:
        bool: True if the log following process terminates validly, False otherwise.

    Raises:
        None explicitly defined, but will handle `KeyboardInterrupt` gracefully during execution.
    """
    if stream not in typing.get_args(T_Stream):
        raise ValueError(f"Invalid stream value: '{stream}'.")

    # Get container name for prefix
    name_result = ctx.run(
        "docker inspect --format='{{.Name}}' %(container)s" % {"container": container_id},
        hide=True,
        warn=True,
    )

    container_name = name_result.stdout.strip().lstrip("/")
    container_name = container_name.removeprefix(f"{project}-").ljust(longest_name + 3, " ")

    prefix = color(f"{container_name} | ")

    re_filter_fn = parse_regex(filter_pattern) if filter_pattern else None

    stdout_handler = (
        LineBufferHandler(f"{prefix}out | " if verbose else prefix, sys.stdout, filter_fn=re_filter_fn)
        if stream in ("out", "stdout", "")
        else NoopHandler()
    )
    stderr_handler = (
        LineBufferHandler(f"{prefix}err | " if verbose else prefix, sys.stderr, filter_fn=re_filter_fn)
        if stream in ("out", "stdout", "")
        else NoopHandler()
    )

    # Loop until container state is 'exited'
    process: Optional[Promise] = None
    runner: Optional[Runner] = None
    while True:
        try:
            # Check container state
            result = ctx.run(
                "docker inspect --format='{{.State.Status}}' %(container)s" % {"container": container_id},
                hide=True,
                warn=True,
            )

            if result.failed:
                # machine is dead
                return False

            # Follow logs with timestamps, starting from last_timestamp if available
            args = ["docker", "logs", "--follow", container_id]
            if timestamps:
                args.append("--timestamps")

            # If we have a last timestamp, use it to start from where we left off
            if since:
                args.extend(("--since", since))

            # Run the docker logs command with our watcher
            cmd = shlex.join(args)
            process = ctx.run(cmd, pty=True, warn=True, asynchronous=True)
            runner = process.runner

            try:
                while not runner.process_is_finished:
                    # start loop - check for stop event
                    if stop_event and stop_event.is_set():
                        return True

                    while runner.stdout:
                        stdout_handler.process(runner.stdout.pop(0))

                    while runner.stderr:
                        stderr_handler.process(runner.stderr.pop(0))

                    time.sleep(0.1)
            except ChildProcessError:
                # --since <datetime> includes rows at that datetime so `dt.timedelta(microseconds=1)` is added:
                since = (dt.datetime.now() + dt.timedelta(microseconds=1)).isoformat()
                time.sleep(0.1)
                continue

        except KeyboardInterrupt:
            # Cancel the process if it's still running
            if runner and not runner.process_is_finished:
                runner.stop()
                runner.kill()
            return True

    # idk how we got here
    return False


@task(
    aliases=("log",),
    iterable=["service"],
    flags={
        "show_all": ("all", "a"),
        "filter_pattern": ("filter", "p"),  # -p for pattern, -f is already for follow
    },
    help={
        "service": "What services to follow. "
        "Defaults to services in the `log` section of `.toml`, can be applied multiple times. ",
        "show_all": "Ignore --service and show all service logs (same as `-s '*'`).",
        "follow": "Keep scrolling with the output (default, use --no-follow or --limit <n> or --sort to disable).",
        "timestamps": "Add timestamps (on by default, use --no-timestamps to disable)",
        "limit": "Start with how many lines of history, don't follow.",
        "sort": "Sort the output by timestamp: forced timestamp and mutual exclusive with follow.",
        "since": "Filter by age (2024-05-03T12:00:00, 1 hour, now); in UTC",
        "new": "Don't show old entries (conflicts with since, same as --since now)",
        "stream": "Filter by stdout/stderr (defaults to both), only used when following",
        "filter_pattern": "Search by term or regex, only used when following",
        "verbose": "Show slightly more info, like full timestamps.",
    },
)
def logs(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    follow: bool = True,
    limit: Optional[int] = None,
    sort: bool = False,
    show_all: bool = False,
    verbose: bool = False,
    timestamps: bool = True,
    since: Optional[str] = None,
    new: bool = False,
    stream: T_Stream = "",
    filter_pattern: str = "",
) -> list[bool]:
    """Smart docker logging"""

    if new and since:
        raise ValueError("Cannot use --new and --since together")
    if new:
        since = "1s"

    if sort and follow:
        raise ValueError("--sort is mutually exclusive with following logs")

    if show_all:
        services = service_names([], default="all")
    else:
        services = service_names(service or [], default="logs")

    if limit or not follow or sort:
        if filter:
            raise ValueError("--filter is exclusive with --limit, --no-follow and --sort")
        # use basic logs
        cmdline = [f"{DOCKER_COMPOSE} logs", f"--tail={limit or 500}"]
        cmdline.extend(services)
        if sort or timestamps:
            # add timestamps
            cmdline.append("-t")

        if sort:
            cmdline.append(r'| sed -E "s/^([^|]*)\|([^Z]*Z)(.*)$/\2|\1|\3/" | sort')

        if since:
            cmdline.extend(["--since", since])

        return [ctx.run(" ".join(cmdline), echo=verbose, pty=True).ok]

    # else use fancy logs

    # now find containers for these services:
    # -> `py4web` can map to `py4web-1, py4web-2` etc
    promises: list[futures.Future[bool]] = []
    colors = rainbow()
    containers = get_docker_info(ctx, services)

    if not containers:
        cprint(f"No running containers found for services {services}", color="red")
        exit(1)
    elif len(containers) != len(services):
        cprint("Amount of requested services does not match the amount of running containers!", color="yellow")

    # for adjusting the | location
    longest_name = max([len(_["Service"]) for _ in containers.values()])

    with futures.ThreadPoolExecutor() as executor:
        stop_event = threading.Event()

        for service in services:
            for container_id in ctx.run(f"{DOCKER_COMPOSE} ps -aq {service}", hide=True).stdout.split("\n"):
                if not (container_info := containers.get(container_id)):
                    # empty or whitespace only
                    continue

                future = executor.submit(
                    follow_logs,
                    ctx,
                    container_id,
                    container_info["Project"],
                    longest_name,
                    next(colors),
                    since,
                    verbose,
                    timestamps,
                    stream,
                    filter_pattern,
                    stop_event,
                )
                promises.append(future)

        # Wait for all futures to complete
        # This mimics the original join_all behavior to return the list of results
        try:
            return [promise.result() for promise in promises]
        except KeyboardInterrupt:
            print("Ctrl-C pressed, stopping log threads...")
            stop_event.set()
            return []


def start_logs(c: Context, service: typing.Collection[str] = None, args: str = ""):
    """
    Normal edwh logs can't just be called with `edwh.tasks.logs` so this wrapper makes it easier.

    (otherwise `logs` will try to elevate permissions and get confused due to not being called directly)
    """
    service = service_names(service or ())

    args = " ".join(f"-s {s}" for s in service) + f" {args}"

    return c.run(f"edwh logs {args}", pty=True)


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
    hookable=True,
)
def stop(ctx: Context, service: typing.Collection[str] | None = None) -> None:
    """
    Stops services using docker-compose stop.
    """
    service = service_names(service or [])
    ctx.run(f"{DOCKER_COMPOSE} stop {' '.join(service)}")


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
    hookable=True,
)
def down(ctx: Context, service: typing.Collection[str] | None = None) -> None:
    """
    Stops services using docker-compose down.
    """
    service = service_names(service or []) if service else []

    ctx.run(f"{DOCKER_COMPOSE} down {' '.join(service)}", pty=True)


@task(
    iterable=["service"],
)
def restart(c: Context, service: typing.Collection[str] = None, quiet: bool = False, force: bool = False):
    """
    Restart Docker services by sending termination signals (ctrl-c/SIGINT; if force: SIGKILL, SIGTERM).

    Defaults to 'py4web' if no services specified.
    Shows logs unless 'quiet' flag is enabled.

    Arguments:
        c (Context): The execution context.
        service (Collection[str], optional): A collection of service names to restart. Defaults to restarting
            the 'py4web' service.
        quiet (bool): A flag indicating whether to suppress logs display after restarting services.
        force: send SIGKILL + SIGTERM instead of SIGINT

    Raises:
        Executes a system command to restart the desired services. Should be used within an environment that supports this
        functionality.

    Returns:
        None
    """
    service = service_names(service or ["py4web"])

    service_filter = "|".join(service)
    kill = "kill -15 1 || kill -9 1" if force else "kill -2 1"
    command = (
        'docker ps --filter "name=%(name)s" --format "{{.Names}}" | '
        'xargs -I {} docker exec {} sh -c "%(kill)s"' % dict(name=service_filter, kill=kill)
    )

    c.run(command)

    if not quiet:
        start_logs(c, service)


@task(
    hookable=True,
)
def upgrade(ctx: Context, build: bool = False) -> None:
    if build:
        ctx.run(f"{DOCKER_COMPOSE} build")
    else:
        ctx.run(f"{DOCKER_COMPOSE} pull")
    stop(ctx)
    ctx.run(f"{DOCKER_COMPOSE} up -d")


@task(
    help=dict(
        yes="Don't ask for confirmation, just do it. "
        "(unless requirements.in files are found and the `edwh-pipcompile-plugin` is not installed)",
        skip_compile="Skip the compilation of requirements.in files to requirements.txt files (e.g. for PRD).",
    ),
    hookable=True,
)
def build(ctx: Context, yes: bool = False, skip_compile: bool = False, pull: bool = True) -> None:
    """
    Build all services.

    Will test for the presence of `edwh-pipcompile-plugin` and use it to compile
    requirements.in files to requirements.txt files in child directories.
    """
    # Path.cwd() uses absolute paths, Path() is the same but relative
    reqs = list(Path().rglob("*/*.in"))

    if pip_compile := get_task(ctx, "pip.compile"):
        with_compile = not skip_compile
    else:
        with_compile = False

        cprint("`edwh-pipcompile-plugin` not found, unable to compile requirements.in files.", "red")
        cprint("💡 Install with `edwh plugin.add pipcompile`", "blue")
        print()
        print("Possible files to compile:")
        for req in reqs:
            print(" * ", req)

    if not (state_of_development := get_env_value("STATE_OF_DEVELOPMENT", "")):
        cprint("Warning: No SOD found. Add STATE_OF_DEVELOPMENT to the .env file", "yellow")

    is_dev = state_of_development == "ONT"

    if not reqs:
        cprint("No .in files found to compile!", "yellow")
    elif with_compile and pip_compile is not None and is_dev:
        for idx, req in enumerate(reqs, 1):
            reqtxt = req.parent / "requirements.txt"
            cprint(
                f"{idx}/{len(reqs)}: working on {req}",
                "blue",
            )
            missing = not reqtxt.exists()
            outdated = not missing and reqtxt.stat().st_ctime < req.stat().st_ctime

            if missing or outdated:
                print("The .txt file is outdated." if outdated else "requirements.txt doesn't exist.")

                question = f"compile {req}? [Yn]"
                if outdated:
                    question = f"re{question}"  # recompile

                if yes or confirm(question, default=True):
                    pip_compile(ctx, str(req.parent))
            else:
                print("still current")
    else:
        print("Compilation of requirements.in files skipped.")

    print()
    prompt = "Pull and build docker images? [yN]" if pull else "Build docker images? [yN]"

    if yes or is_dev or confirm(prompt, default=False):
        if pull:
            ctx.run(f"{DOCKER_COMPOSE} pull --ignore-buildable", pty=True)

        ctx.run(f"{DOCKER_COMPOSE} build", pty=True, env=dict(COMPOSE_BAKE="true"))


@task(
    help=dict(
        service="Service to rebuild, can be used multiple times, handles wildcards.",
        force_rebuild="uses --no-cache option for docker-compose build",
    ),
    iterable=["service"],
)
def rebuild(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    force_rebuild: bool = False,
) -> None:
    """
    Downs ALL services, then rebuilds services using docker-compose build.
    """
    ctx.run(f"{DOCKER_COMPOSE} down")
    services = service_names(service)

    cache_flag = "--no-cache" if force_rebuild else ""
    services_str = " ".join(services)
    ctx.run(f"{DOCKER_COMPOSE} build {cache_flag} {services_str}")


@task()
def docs(ctx: Context, reinstall: bool = False) -> bool:
    """
    Local hosted mkdocs documentation.

    Installs mkdocs if unavailable.
    """
    if reinstall:
        print("Installing mkdocs and dependencies...")
        ok = True
        ctx.run("pipx uninstall mkdocs", hide=True, warn=True)

        ran = ctx.run("pipx install mkdocs", hide=True, warn=True)
        ok &= bool(ran and ran.ok)
        ran = ctx.run(
            "pipx inject mkdocs mkdocs-material plantuml-markdown",
            hide=True,
            warn=True,
        )
        ok &= bool(ran and ran.ok)
        print("result:", ok)
        return ok
    else:
        ran = ctx.run("mkdocs serve", warn=True)
        if not (ran and ran.ok) and docs(ctx, reinstall=True):
            return docs(ctx)

    return False


# noinspection PyUnusedLocal
@task()
def zen(_: Context) -> None:
    """Prints the Zen of Python"""
    # noinspection PyUnresolvedReferences
    import this  # noqa


@task()
def whoami(ctx: Context) -> None:
    """
    Debug method to determine user and host name.
    """
    ran = ctx.run("whoami", hide=True)
    i_am = ran.stdout.strip() if ran else ""

    ran = ctx.run("hostname", hide=True)
    my_location = ran.stdout.strip() if ran else ""

    print(f"{i_am} @ {my_location}")


@task()
def completions(_: Context) -> None:
    """
    Prints the script to enable shell completions.
    """
    print("Put this in your .bashrc:")
    print("---")
    print('eval "$(edwh --print-completion-script bash)"')
    print("---")


@task(
    hookable=True,
)
def version(ctx: Context) -> None:
    """
    Show edwh app version and docker + compose version.
    """
    from ewok.__about__ import __version__ as ewok_version

    print("edwh version", edwh_version)
    print("ewok version", ewok_version)
    print("Python version", sys.version.split(" ")[0])
    ctx.run("docker --version")
    ctx.run(f"{DOCKER_COMPOSE} version")


# for meta tasks such as `plugins` and `self-update`, see meta.py


@task(
    name="help",
    help={
        "about": "Plugin/Namespace or Subcommand you would like to see help about. "
        "Use an empty string ('') to see help about everything."
    },
)
def show_help(ctx: Context, about: str) -> None:
    """
    Show helpful information about a plugin or command.

    Similar to `edwh {about} --help` but that does not work for whole plugins/namespaces.
    """
    # first check if 'about' is a plugin/namespace:
    if ns := ewok.find_namespace(ctx, about):
        info = ns.serialized()

        print("--- namespace", ns.name, "---")
        print(info["help"] or "")

        plugin_commands = []
        for subtask in info["tasks"]:
            if aliases := subtask["aliases"]:
                aliases = ", ".join(aliases)
                aliases = f"({aliases})"
            else:
                aliases = ""

            cmd = f"{about}.{subtask['name']}"

            plugin_commands.append(" ".join([cmd, aliases, "\t", subtask["help"] or ""]))

        print_aligned(plugin_commands)
    else:
        # just run edwh --help <subcommand>:
        ctx.run(f"edwh --help {about}")


@task(
    name="discover",
    help={
        "du": "Show disk usage per folder",
        "exposes": "Show exposed ports",
        "ports": "Show ports",
        "host_labels": "Show host clauses from traefik labels",
        "short": "Oneline summary",
        "show_settings": "show settings per folder",
        "as_json": "output json",
    },
    flags={"show_settings": ("settings", "show-settings"), "as_json": ("j", "json", "as-json")},  # -s is for short
)
def task_discover(
    ctx: Context,
    du: bool = False,
    exposes: bool = False,
    ports: bool = False,
    host_labels: bool = True,
    short: bool = False,
    show_settings: bool = False,
    as_json: bool = False,
) -> None:
    """Discover docker environments per host.

    Use ansi2txt to save readable output to a file.
    """
    return discover(
        ctx,
        du=du,
        exposes=exposes,
        ports=ports,
        host_labels=host_labels,
        short=short,
        as_json=as_json,
        settings=show_settings,
    )


@task()
def ew_self_update(ctx: Context) -> None:
    """Update edwh to the latest version."""
    ctx.run("~/.local/bin/edwh self-update")
    ctx.run("~/.local/bin/edwh self-update")


@task()
def migrate(ctx: Context, force: bool = False) -> None:
    if force:
        clean_flags(ctx)

    up(ctx, service=["migrate"], tail=True)


@task()
def migrations(ctx: Context) -> None:
    ctx.run(f"{DOCKER_COMPOSE} run --rm migrate migrate --list")


def stop_remove_container(ctx: Context, container_name: str) -> bool:
    ran = ctx.run(f"{DOCKER_COMPOSE} rm -vf --stop {container_name}", warn=True)
    return bool(ran and ran.ok)


def stop_remove_containers(ctx: Context, *container_names: str) -> list[bool]:
    return [stop_remove_container(ctx, _) for _ in container_names]


@task()
def clean_redis(_: Context, db_count: int = 3) -> None:
    import redis as r

    env = read_dotenv(Path(".env"))
    for db in range(db_count):
        redis_client = r.Redis("localhost", int(env["REDIS_PORT"]), db)
        print(f"Removing {len(redis_client.keys())} keys")
        for key in redis_client:  # type: ignore
            del redis_client[key]
        redis_client.close()


@task()
def clean_flags(_: Context, flag_dir: str = "migrate/flags"):
    flag_dir_path = pathlib.Path(flag_dir)

    for flag_file in flag_dir_path.glob("*.complete"):
        print("removing", flag_file)
        flag_file.unlink()


@task()
def clean_postgres(ctx: Context, yes: bool = False) -> None:
    # assumes pgpool with pg-0, pg-1 and optionally pg-stats right now!
    yes or confirm(
        "Are you sure you want to wipe the database? This can not be undone [yes,NO]",
        allowed={"yes"},  # strict yes, not just y !!!
        strict=True,  # raises RuntimeError
    )

    # clear backend flag files
    clean_flags(ctx)

    config = TomlConfig.load()
    assert config, "Couldn't set up toml config -> can't continue clean!"

    # find the images based on the instances
    containers = find_containers_ids(ctx, *config.services_db)
    pg_data_volumes = []
    for container_name, container_ids in containers.items():
        if not container_ids:
            # probably missing (such as pg-1, pg-stats in some environments)
            continue

        for container_id in container_ids:
            info = docker_inspect(ctx, container_id)[0]
            pg_data_volumes.extend([mount["Name"] for mount in info["Mounts"] if "Name" in mount])

    # stop, remove the postgres instances and remove anonymous volumes
    stop_remove_containers(ctx, *containers)

    # remove images after containers have been stopped and removed
    if pg_data_volumes:
        print("removing", pg_data_volumes)
        ctx.run("docker volume rm " + " ".join(pg_data_volumes), warn=True)
    else:
        cprint("No data volumes to remove!", color="yellow")


@task(
    flags={"clean_all": ("all", "a")},
    hookable=True,
)
def clean(
    ctx: Context,
    clean_all: bool = False,
    db: bool = False,
    postgres: bool = False,
    redis: bool = False,
    yes: bool = False,
) -> None:
    """Rebuild the databases, possibly rebuild microservices.

    Execution:
    0. build microservices (all, microservices)
       if force_rebuild:
         does not use docker-image cache, thus refreshing even with the same backend version.
         use this is you wish to rebuild the same backend. Easier and faster to use fix: or perf: in the backend...
    1. stopping postgres instances (all, db, postgres)
    2. removing volumes (all, db, postgres)
    3. rebooting postgres instances (all, db, postgres)
    4. ~~purge redis instances (all, redis)~~ IGNORED

    Removes all ../backend_config/*.complete flags to allow migrate to function properly
    """
    print("-------------------CLEAN -------------------------")
    if clean_all or db or postgres:
        clean_postgres(ctx, yes=yes)

    if clean_all or redis:
        clean_redis(ctx)


@task(aliases=("whipe-db",), flags={"clean_all": ("all", "a")})
def wipe_db(ctx: Context, clean_all: bool = False, flag_path: str = "migrate/flags", yes: bool = False) -> None:
    """
    Wipes postgres volumes.
    Does not start migrate automatically, use `edwh wipe-db migrate up` for a full recovery flow.

    When using a whitelabel-based environment,
        you may also use `edwh local.recover-devdb` (from ./migrate/data/snapshot)
    """
    # 1 + 2. just 'create' without starting anything:
    ctx.run(f"{DOCKER_COMPOSE} create")

    # 3. start cleaning up
    for p in Path(flag_path).glob("migrate-*.complete"):
        p.unlink()

    clean(ctx, db=True, clean_all=clean_all, yes=yes)
    down(ctx)  # remove old containers too


@task()
def show_config(_: Context) -> None:
    """
    Show the current values from .toml after loading.
    """
    config = TomlConfig.load()
    cprint(f"TomlConfig: {json.dumps(config.__dict__, default=str, indent=2) if config else 'None'}")


@task()
def change_config(c: Context) -> None:
    """
    Change the settings in .toml
    """
    build_toml(c, overwrite=True)


@task()
def debug(_: Context) -> None:
    print(get_env_value("IS_DEBUG", "0"))


@task(aliases=("ew",))
def edwh(_: Context) -> None:
    """
    Do absolutely nothing.

    For oopsies like `ew ew up logs`
    """
    print("Hehe you silly goose", file=sys.stderr)


@task()
def sleep(_: Context, n: str) -> None:
    try:
        totaltime = int(n)
    except ValueError as e:
        raise TypeError("`ew sleep <n: int>` requires an amount of seconds to sleep.") from e

    for remaining in range(totaltime, 0, -1):
        print("\r", f"Sleeping for: {remaining} seconds", end=" ", flush=True)
        time.sleep(1)

    print("\r", "Sleeping for: 0 seconds", end="\n")


def find_ruff() -> str:
    """
    Use ruff's own logic to find the required binary.
    """
    from ruff import __main__ as ruff

    return ruff.find_ruff_bin()


@task()
def lint(ctx: Context, directory: Optional[str] = None, select: str = "", fix: bool = False):
    """
    Lint code with `ruff`.

    Args:
        ctx: invoke context
        directory: where to look for code
        select: specific lints to check
        fix: try to fix (some) issues automatically
    """
    directory = directory or "."

    ruff = find_ruff()

    command = [ruff, "check", directory, "--quiet"]
    if select:
        command.append(f"--select {select}")
    if fix:
        command.append("--fix")

    color: Color = "green" if run_pty(ctx, *command) else "red"
    cprint("⬤ ruff", color=color)


@task(aliases=("format",))
def fmt(
    ctx: Context,
    isort: bool = True,
    ioptimize: bool = False,
    reformat: bool = True,
    directory: Optional[str] = None,
    file: Optional[str] = None,
    quiet: bool = False,
):
    """
    Format your Python code with `ruff`, including import sorting (isort).

    `ioptimize` would remove unused imports, but that functionality in `ruff` doesn't seem to work right now
        -> so only display problems for now.

    `file` and `directory` have the same behavior, the different names are there for sugar.
    """
    if file and directory:
        raise ValueError("Conflicting arguments --file and --directory. Please pick one, the behavior is the same.")

    target = directory or file or "."

    ruff = find_ruff()

    color: Color

    if isort:
        color = "green" if run_pty_ok(ctx, ruff, f"check --select I --fix {target} --quiet") else "red"
        cprint("⬤ isort", color=color)

    if reformat:
        # note: ruff format --quiet also hides what's wrong, so instead pipe stdout to dev null and only show stderr:
        color = "green" if run_pty_ok(ctx, ruff, f"format {target} > /dev/null") else "red"
        cprint("● reformat", color=color)

    if not quiet and not ioptimize:
        # print out unused imports:
        try:
            # grep remove the --fix suggestion since we have other cli args;
            # grep piping removes the nice coloring unless we force it;
            # pipefall would forward ruff's exit code but if grep has no output, it exits with 1.
            # so we do this fuckery:
            ctx.run(
                f"""
                    ruff_output=$(FORCE_COLOR=1 {ruff} check --select F401 {target})
                    ruff_exit=$?
                    echo "$ruff_output" | grep -v -E '(`--fix`|^All checks passed!$)' || true
                    exit $ruff_exit""",
                pty=True,
            )
        except invoke.exceptions.UnexpectedExit as e:
            print(e.result.return_code)
            cprint(
                "Hint: unused imports can be removed with --ioptimize; this check can be skipped with --quiet",
                "blue",
            )

    elif ioptimize:
        # else, autofix F401 = unused-import
        color = "green" if run_pty_ok(ctx, ruff, f"check --select F401 {target} --fix --quiet") else "red"
        cprint("⬤ ioptimize", color=color)
