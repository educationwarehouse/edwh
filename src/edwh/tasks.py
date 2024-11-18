import contextlib
import fnmatch
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import typing
import warnings
from asyncio import CancelledError
from collections import Counter
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Optional

import anyio
import invoke
import tabulate
import tomlkit  # can be replaced with tomllib when 3.10 is deprecated
import yaml
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
from .discover import discover, get_hosts_for_service  # noqa

# noinspection PyUnresolvedReferences
# ^ keep imports for backwards compatibility (e.g. `from edwh.tasks import executes_correctly`)
from .helpers import interactive_selected_checkbox_values  # noqa
from .helpers import (  # noqa
    AnyDict,
    confirm,
    dc_config,
    dump_set_as_list,
    executes_correctly,
    execution_fails,
    fabric_read,
    fabric_write,
    flatten,
)
from .helpers import generate_password as _generate_password
from .helpers import (  # noqa
    interactive_selected_radio_value,
    noop,
    print_aligned,
    shorten,
)
from .improved_invoke import ImprovedTask as Task
from .improved_invoke import improved_task as task
from .improved_logging import parse_regex, parse_timedelta, rainbow, tail

# noinspection PyUnresolvedReferences
# ^ keep imports for other tasks to register them!
from .meta import plugins, self_update  # noqa


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


def task_for_namespace(namespace: str, task_name: str) -> Task | None:
    """
    Get a task by namespace + task_name.

    Example:
        namespace: local, task_name: setup
    """
    from .cli import collection

    if ns := collection.collections.get(namespace):
        return typing.cast(Task, ns.tasks.get(task_name))

    return None


def task_for_identifier(identifier: str) -> Task | None:
    from .cli import collection

    return collection.tasks.get(identifier)


def get_task(identifier: str) -> Task | None:
    """
    Get a task by the identifier you would use in the terminal.

    Example:
        local.setup
    """

    if "." in identifier:
        return task_for_namespace(*identifier.split("."))
    else:
        return task_for_identifier(identifier)


def exec_setup_in_other_task(c: Context, run_setup: bool, **kw: typing.Any) -> bool:
    """
    Run a setup function in another task.py.
    """
    if local_setup := task_for_namespace("local", "setup"):
        if run_setup:
            local_setup(c, **kw)

        return True
    else:
        print("No (local) setup function found in your nearest tasks.py", file=sys.stderr)

    return False


def exec_up_in_other_task(c: Context, services: list[str]) -> bool:
    """
    Run a setup function in another task.py.
    """
    if local_up := task_for_namespace("local", "up"):
        local_up(c, services)

        return True
    else:
        print("No (local) up function found in your nearest tasks.py", file=sys.stderr)

    return False


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
    include_celeries_in_minimal: str  # 'true' or 'false'
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


@dataclass
class TomlConfig:
    config: ConfigTomlDict
    all_services: list[str]
    celeries: list[str]
    services_minimal: list[str]
    services_log: list[str]
    services_db: list[str]
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
        if config["services"].get("include_celeries_in_minimal", "false") == "true":
            minimal_services += celeries

        tomlconfig_singletons[singleton_key] = instance = TomlConfig(
            config=config,
            all_services=all_services,
            celeries=celeries,
            services_minimal=minimal_services,
            services_log=config["services"]["log"],
            services_db=config["services"]["db"],
            dotenv_path=Path(config.get("dotenv", {}).get("path", dotenv_path or DEFAULT_DOTENV_PATH)),
        )
        return instance


def process_env_file(env_path: Path) -> dict[str, str]:
    items: dict[str, str] = {}
    if not env_path.exists():
        return items

    with env_path.open(mode="r") as env_file:
        for line in env_file:
            # remove comments and redundant whitespace
            line = line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                # just a comment, skip
                # or key without value? invalid, prevent crash:
                continue

            # convert to tuples
            k, v = line.split("=", 1)

            # clean the tuples and add to dict
            items[k.strip()] = v.strip()
    return items


def read_dotenv(env_path: Path = DEFAULT_DOTENV_PATH) -> dict[str, str]:
    """
    Read .env file from env_path and return a dict of key/value pairs.

    If env_path is not given, TomlConfig.load().dotenv_path is used.

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

    items = process_env_file(env_path)

    _dotenv_settings[cache_key] = items
    return items


# noinspection PyDefaultArgument
def warn_once(
    warning: str, previously_shown: list[str] = [], color: Optional[Color] = None, **print_kwargs: typing.Any
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


def check_env(
    key: str,
    default: Optional[str],
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

    if force_default:
        value = default or ""
    else:
        response = input(f"Enter value for {key} ({comment})\n default=`{default}`: ")
        if allowed_values and response not in allowed_values:
            raise ValueError(f"Invalid value '{response}'. Please choose one of {allowed_values}")
        value = response.strip() or default or ""

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


def set_env_value(path: Path, target: str, value: str) -> None:
    """
    Update/set environment variables in the .env file, keeping comments intact.

    set_env_value(Path('.env'), 'SCHEMA_VERSION', schemaversion)

    Args:
        path: pathlib.Path designating the .env file
        target: key to write, probably best to use UPPERCASE
        value: string value to write, or anything that converts to a string using str()
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
            # add the new tuple to the lines
            outlines.append(f"{key}={value}")
            geschreven = True
        else:
            # or leave it as it is
            outlines.append(line)
    if not geschreven:
        outlines.append(f"{target.strip().upper()}={value.strip()}")
    with path.open(mode="w") as env_file:
        env_file.write("\n".join(outlines))
        env_file.write("\n")


# def print_services(services: list, selected_services: list = None, warn: str = None):
#     """
#     print all the services that are in the docker-compose.yml
#
#     :param services: docker services that are in the docker-compose.yml
#     :return: a list of all services in the docker-compose.yml
#     """
#     if warn is not None:
#         print(warn)
#
#     print("\nservices:")
#     for index in range(len(services)):
#         if services[index] == "":
#             continue
#         print(f"{index + 1}: {services[index]}")
#
#     if selected_services is None:
#         return
#
#     print("\nselected services:")
#     for index in range(len(selected_services)):
#         print(f"{index + 1}:", selected_services[index])


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
    all_services: list[str], filename: str | Path = DEFAULT_TOML_NAME, overwrite: bool = False
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
            "true" if confirm("do you want to include celeries in minimal(Y/n): ", default=True) else "false"
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
    c: Optional[Context] = None, dc_path: str | Path = "docker-compose.yml"
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

    sudo_pass = getpass("Please enter the sudo password: ")
    c.config.sudo.password = sudo_pass

    try:
        result = c.sudo("echo ''", warn=True, hide=True)
        if not (result and result.ok):
            raise invoke.exceptions.AuthFailure(result, "sudo")

        cprint("Sudo password accepted!", color="green", file=sys.stderr)
        return True
    except invoke.exceptions.AuthFailure as e:
        cprint(str(e), color="red", file=sys.stderr)
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


@task(
    pre=[require_sudo],
    help={
        "run_local_setup": "executes local_tasks setup (default is True)",
        "new_config_toml": "will REMOVE and create a new config.toml file",
    },
)
def setup(c: Context, run_local_setup: bool = True, new_config_toml: bool = False, _retry: bool = False) -> bool:
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

    if not dc_path.exists():
        cprint("docker-compose file is missing, setup could not be completed!", color="red")
        return False

    print("getting services...")

    try:
        # run `docker compose config` to build a yaml with all processing done, include statements included.
        build_toml(c)
    except Exception as e:
        cprint(
            f"Something went wrong trying to create a {DEFAULT_TOML_NAME} from docker-compose.yml ({e})", color="red"
        )
        # this could be because 'include' requires a variable that's setup in local task, so still run that:
    exec_setup_in_other_task(c, run_local_setup)
    return True


@task(
    pre=[require_sudo],
)
def test_sudo(c):
    print(c.sudo("whoami"))


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
            print(f"{project :>20} : {value}")
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
        "as_json": ["j", "json", "as-json"],
        "fuzz_threshold": ["t", "fuzz-threshold"],
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
            info = inspect(ctx, container_id)
            container = info["Name"]
            lines.extend(
                dict(container=container, volume=volume)
                for volume in [_["Name"] for _ in info["Mounts"] if _["Type"] == "volume"]
            )

    print(tabulate.tabulate(lines, headers="keys"))


# noinspection PyShadowingNames
@task(
    help=dict(
        service="Service to up, defaults to .toml's [services].minimal. "
        "Can be used multiple times, handles wildcards.",
        build="request a build be performed first",
        quickest="restart only, no down;up",
        stop_timeout="timeout for stopping services, defaults to 2 seconds",
        tail="tails the log of restart services, defaults to False",
        clean="adds `--renew-anon-volumes --build` to `docker-compose up` command ",
    ),
    iterable=["service"],
    flags={
        "tail": ["tail", "logs", "l"],  # instead of -a; NOTE: 'tail' must be first (matches parameter name)
    },
)
def up(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    build: bool = False,
    quickest: bool = False,
    stop_timeout: int = 2,
    tail: bool = False,
    clean: bool = False,
    show_settings: bool = True,
) -> None:
    """Restart (or down;up) some or all services, after an optional rebuild."""
    config = TomlConfig.load()
    # recalculate the hash and save it, so with the next up, migrate will see differences and start migration
    set_env_value(DEFAULT_DOTENV_PATH, "SCHEMA_VERSION", calculate_schema_hash())
    # test for --service arguments, if none given: use defaults
    services = service_names(service or (config.services_minimal if config else []))
    services_ls = " ".join(services)

    if build:
        ctx.run(f"{DOCKER_COMPOSE} build {services_ls}")
    if quickest:
        ctx.run(f"{DOCKER_COMPOSE} restart {services_ls}")
    else:
        ctx.run(f"{DOCKER_COMPOSE} stop -t {stop_timeout}  {services_ls}")
        ctx.run(f"{DOCKER_COMPOSE} up {'--renew-anon-volumes --build' if clean else ''} -d {services_ls}")

    exec_up_in_other_task(ctx, services)
    if show_settings:
        show_related_settings(ctx, services)
    if tail:
        ctx.run(f"{DOCKER_COMPOSE} logs --tail=10 -f {services_ls}")


@task()
def ps_all(ctx: Context):
    """
    Show all active (docker compose) environments.
    """
    dockers = ctx.run('docker ps --format "{{.Names}}"', hide=True).stdout

    projects = Counter(_.split("-")[0] for _ in dockers.split("\n") if _ and "-" in _)
    projects = {k: str(v) for k, v in projects.items()}

    print(tabulate.tabulate(projects.items(), headers=["Project", "Dockers"], tablefmt="pipe"))


@task(
    iterable=["service", "columns"],
    help=dict(
        service="Service to query, can be used multiple times, handles wildcards.",
        quiet="Only show container ids. Useful for scripting.",
        columns="Which columns to display?",
        full_command="Don't truncate the command.",
    ),
    flags={
        "show_all": ["all", "a"],
    },
)
def ps(
    ctx: Context,
    quiet: bool = False,
    service: typing.Collection[str] | None = None,
    columns: typing.Collection[str] | None = None,
    full_command: bool = False,
    show_all: bool = False,
) -> None:
    """
    Show process status of services.
    """
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
    if full_command:
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
    selected_columns = list(columns or []) or ["Name", "Command", "State", "Ports"]

    for service_json in ps_output.split("\n"):
        if not service_json:
            # empty line
            continue

        service_dict = json.loads(service_json)
        service_dict = {k: v for k, v in service_dict.items() if k in selected_columns}
        if not full_command:
            service_dict["Command"] = shorten(service_dict["Command"], 50)

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
    ctx.run(f'{DOCKER_COMPOSE} ls {"-q" if quiet else ""}')


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


async def logs_improved_async(
    c: Context,
    service: typing.Collection[str] | None = None,
    since: Optional[str] = None,
    new: bool = False,
    stream: Optional[str] = None,
    re_filter: Optional[str] = None,
    timestamps: bool = True,
    verbose: bool = False,
) -> None:
    if new:
        since = "now"

    if since:
        since = parse_timedelta(since)

    re_filter_fn = parse_regex(re_filter) if re_filter else None

    services = service_names(service, default="logs")
    containers = get_docker_info(c, services)

    if not containers:
        cprint(f"No running containers found for services {services}", color="red")
        exit(1)
    elif len(containers) != len(services):
        cprint("Amount of requested services does not match the amount of running containers!", color="yellow")

    # for adjusting the | location
    longest_name = max([len(_["Service"]) for _ in containers.values()])

    colors = rainbow()

    print("---", file=sys.stderr)
    async with anyio.create_task_group() as task_group:
        for container, container_info in containers.items():
            # ontwikkelstraat-py4web-1 -> py4web-1
            # this is slightly different from the original 'service' which is just e.g. 'py4web'
            container_name = (
                container_info["Name"].removeprefix(container_info["Project"] + "-").ljust(longest_name + 3, " ")
            )

            file = f"/var/lib/docker/containers/{container}/{container}-json.log"
            task_group.start_soon(
                tail,  # type: ignore
                {
                    "filename": file,
                    "human_name": container_name,
                    "container_id": container,
                    "stream": stream,
                    "since": since,
                    "re_filter": re_filter_fn,
                    "color": next(colors),
                    "timestamps": timestamps,
                    "verbose": verbose,
                    "state": container_info["State"],
                },
            )


def inspect(ctx: Context, container_id: str) -> AnyDict:
    """
    Docker inspect a container by ID and get the first result.

    :raise EnvironmentError if docker inspect failed.
    """
    ran = ctx.run(f"docker inspect {container_id}", hide=True, warn=True)
    if ran and ran.ok:
        return typing.cast(AnyDict, json.loads(ran.stdout)[0])
    else:
        print(ran.stderr if ran else "-")
        raise EnvironmentError(f"docker inspect {container_id} failed")


def elevate(target_command: str) -> None:
    if os.geteuid() == 0:
        return

    # not root, try again with sudo:
    split_idx = sys.argv.index(target_command)
    relevant_args = sys.argv[split_idx:]
    subprocess.call(["sudo", sys.argv[0], *relevant_args])
    exit(0)


def logs_improved(
    c: Context,
    service: typing.Collection[str] | None = None,
    since: Optional[str] = None,
    stream: Optional[str] = None,
    filter: Optional[str] = None,
    timestamps: bool = True,
    verbose: bool = False,
) -> None:
    with contextlib.suppress(CancelledError, KeyboardInterrupt):
        anyio.run(
            lambda *_: logs_improved_async(
                c,
                service=service,
                since=since,
                stream=stream,
                re_filter=filter,
                timestamps=timestamps,
                verbose=verbose,
            )
        )


@task(
    aliases=("log",),
    iterable=["service"],
    help={
        "service": "What services to follow. "
        "Defaults to services in the `log` section of `.toml`, can be applied multiple times. ",
        "all": "Ignore --service and show all service logs (same as `-s '*'`).",
        "follow": "Keep scrolling with the output (default, use --no-follow or --limit <n> or --sort to disable).",
        "timestamps": "Add timestamps (on by default, use --no-timestamps to disable)",
        "limit": "Start with how many lines of history, don't follow.",
        "sort": "Sort the output by timestamp: forced timestamp and mutual exclusive with follow.",
        "since": "Filter by age (2024-05-03T12:00:00, 1 hour, now); in UTC",
        "new": "Don't show old entries (conflicts with since, same as --since now)",
        "stream": "Filter by stdout/stderr (defaults to both), only used when following",
        "filter": "Search by term or regex, only used when following",
        "verbose": "Show slightly more info, like full timestamps.",
    },
)
def logs(
    ctx: Context,
    service: typing.Collection[str] | None = None,
    follow: bool = True,
    limit: Optional[int] = None,
    sort: bool = False,
    all: bool = False,  # noqa A002
    verbose: bool = False,
    timestamps: bool = True,
    since: Optional[str] = None,
    new: bool = False,
    stream: Optional[str] = None,
    filter: Optional[str] = None,
) -> None:
    """Smart docker logging"""

    cmdline = [f"{DOCKER_COMPOSE} logs", f"--tail={limit or 500}"]
    if sort or timestamps:
        # add timestamps
        cmdline.append("-t")

    if new:
        since = "1s"

    if since:
        cmdline.extend(["--since", since])

    if all:
        # -s "*" is the same but `-s *` triggers bash expansion so that's annoying.
        cmdline.extend(service_names([], default="all"))
    else:
        cmdline.extend(service_names(service, default="logs"))

    if sort:
        cmdline.append(r'| sed -E "s/^([^|]*)\|([^Z]*Z)(.*)$/\2|\1|\3/" | sort')
    elif limit:
        # nothing special, just here to prevent follow
        ...
    elif follow:
        # rerun `ew logs` with sudo:
        elevate("logs")
        # only allow follow if not sorting and no limit (tail):
        return logs_improved(
            ctx,
            service="*" if all else service,
            since=since,
            stream=stream,
            filter=filter,
            timestamps=timestamps,
            verbose=verbose,
        )

    ctx.run(" ".join(cmdline), echo=verbose, pty=True)


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
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
)
def down(ctx: Context, service: typing.Collection[str] | None = None) -> None:
    """
    Stops services using docker-compose down.
    """
    service = service_names(service or []) if service else []

    ctx.run(f"{DOCKER_COMPOSE} down {' '.join(service)}", pty=True)


@task()
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
    )
)
def build(ctx: Context, yes: bool = False, skip_compile: bool = False) -> None:
    """
    Build all services.

    Will test for the presence of `edwh-pipcompile-plugin` and use it to compile
    requirements.in files to requirements.txt files in child directories.
    """
    reqs = list(Path(".").rglob("*/requirements.in"))

    if pip_compile := get_task("pip.compile"):
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

    if not reqs:
        cprint("No .in files found to compile!", "yellow")
    elif with_compile and pip_compile is not None and state_of_development == "ONT":
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
    if yes or confirm("Build docker images? [yN]", default=False):
        ctx.run(f"{DOCKER_COMPOSE} build", pty=True)


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


@task()
def version(ctx: Context) -> None:
    """
    Show edwh app version and docker + compose version.
    """
    print("edwh version", edwh_version)
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
    from .cli import collection

    ns: invoke.collection.Collection
    if ns := collection.collections.get(about):  # type: ignore
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

        return print_aligned(plugin_commands)
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
    flags={"show_settings": ["settings", "show-settings"], "as_json": ["j", "json", "as-json"]},  # -s is for short
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


def find_container_id(ctx: Context, container: str) -> Optional[str]:
    if result := ctx.run(f"{DOCKER_COMPOSE} ps -aq {container}", hide=True, warn=True):
        return result.stdout.strip()
    else:
        return None


def find_container_ids(ctx: Context, *containers: str) -> dict[str, Optional[str]]:
    return {container: find_container_id(ctx, container) for container in containers}


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
def clean_flags(ctx: Context, flag_dir: str = "migrate/flags"):
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
    containers = find_container_ids(ctx, *config.services_db)
    pg_data_volumes = []
    for container_name, container_id in containers.items():
        if not container_id:
            # probably missing (such as pg-1, pg-stats in some environments)
            continue

        info = inspect(ctx, container_id)
        pg_data_volumes.extend([mount["Name"] for mount in info["Mounts"] if "Name" in mount])

    # stop, remove the postgres instances and remove anonymous volumes
    stop_remove_containers(ctx, "pg-0", "pg-1", "pgpool", "pg-stats")

    # remove images after containers have been stopped and removed
    if pg_data_volumes:
        print("removing", pg_data_volumes)
        ctx.run("docker volume rm " + " ".join(pg_data_volumes), warn=True)
    else:
        cprint("No data volumes to remove!", color="yellow")


@task(flags={"clean_all": ["all", "a"]})
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


@task(aliases=("whipe-db",), flags={"clean_all": ["all", "a"]})
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

    print("\r", f"Sleeping for: 0 seconds", end="\n")


@task()
def fmt(_: Context, black: bool = True, isort: bool = True, directory: Optional[str] = None):
    """
    Format your Python code with black and isort.
    """
    from su6.cli import do_fix

    exclude = []
    if not black:
        exclude.append("black")
    if not isort:
        exclude.append("isort")

    do_fix(directory=directory, exclude=exclude)
