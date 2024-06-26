import contextlib
import fnmatch
import io
import json
import os
import pathlib
import re
import shutil
import sys
import typing
import warnings
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Optional

import invoke
import tabulate
import tomlkit  # can be replaced with tomllib when 3.10 is deprecated
import yaml
from invoke import Context  # , Task, task
from rapidfuzz import fuzz
from termcolor import colored, cprint

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
from .helpers import (  # noqa
    confirm,
    dc_config,
    dump_set_as_list,
    executes_correctly,
    execution_fails,
)
from .helpers import generate_password as _generate_password
from .helpers import (  # noqa
    interactive_selected_checkbox_values,
    interactive_selected_radio_value,
    noop,
    print_aligned,
)
from .improved_invoke import ImprovedTask as Task
from .improved_invoke import improved_task as task

# noinspection PyUnresolvedReferences
# ^ keep imports for other tasks to register them!
from .meta import plugins, self_update  # noqa


def copy_fallback_toml(
    tomlfile=DEFAULT_TOML_NAME, fallbacks=(LEGACY_TOML_NAME, FALLBACK_TOML_NAME), force: bool = False
):
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
    service_arg: list[str],
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
    # service_arg is specified, filter through all available services:

    for service in service_arg:
        selected.update(fnmatch.filter(config.all_services, service))

    if service_arg and not selected:
        # when no service matches the name, don't return an empty list, as that would `up` all services
        # instead of the wanted list. This includes typos, where a single typo could cause all services to be started.
        cprint(f"ERROR: No services found matching: {service_arg!r}", color="red")
        exit(1)

    return list(selected)


def calculate_schema_hash():
    """
    Calculates the sha1 digest of the files in the shared_code folder.

    When anything is changed, it will have a different hash, so migrate will be triggered.
    """
    import hashlib

    filenames = sorted(Path("./shared_code").glob("**/*"))
    # ignore those pesky __pycache__ folders
    filenames = [_ for _ in filenames if "__pycache__" not in str(_) and _.is_file()]
    hasher = hashlib.sha256(b"")
    for filename in filenames:
        hasher.update(filename.read_bytes())
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
        return ns.tasks.get(task_name)

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


def exec_setup_in_other_task(c: Context, run_setup: bool, **kw) -> bool:
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


_dotenv_settings = {}


def _apply_env_vars_to_template(source_lines: list[str], env: dict) -> list[str]:
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
def apply_dotenv_vars_to_yaml_templates(yaml_path: Path, dotenv_path: Path = DEFAULT_DOTENV_PATH):
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


@dataclass
class TomlConfig:
    config: dict
    all_services: list[str]
    celeries: list[str]
    services_minimal: list[str]
    services_log: list[str]
    dotenv_path: Path

    # __loaded was replaced with tomlconfig_singletons

    @classmethod
    def load(
        cls,
        fname: str | Path = DEFAULT_TOML_NAME,
        dotenv_path: Optional[Path] = None,
        cache: bool = True,
    ):
        """
        Load config toml file, raising an error if it does not exist.

        Since this file should be in .git error suppression is not needed.
        Returns a dictionary with CONFIG, ALL_SERVICES, CELERIES and MINIMAL_SERVICES
        """
        singleton_key = (str(fname), str(dotenv_path))

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

        if not pathlib.Path.exists(config_path):
            setup(invoke.Context())

        with config_path.open() as f:
            config = tomlkit.load(f)

        if "services" not in config:
            setup(invoke.Context())

        for service_name in [
            "minimal",
            "services",
            "include_celeries_in_minimal",
            "log",
        ]:
            if service_name not in config["services"]:
                setup(invoke.Context())

        if config["services"].get("services", "discover") == "discover":
            compose = load_dockercompose_with_includes(dc_path=dc_path)

            all_services = list(compose["services"].keys())
        else:
            all_services = config["services"]["services"]

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
            dotenv_path=Path(config.get("dotenv", {}).get("path", dotenv_path or DEFAULT_DOTENV_PATH)),
        )
        return instance


def process_env_file(env_path: Path) -> dict[str, str]:
    items = {}
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


def read_dotenv(env_path: Path = DEFAULT_DOTENV_PATH) -> dict[str, typing.Any]:
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
def warn_once(warning: str, previously_shown: list[str] = [], color: Optional[str] = None, **print_kwargs: typing.Any):
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
    toml_path: None = None,
):
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
            "but only 'suffix' will be used since 'postfix' is just an alias!"
        )

    suffix = suffix or postfix

    response = input(f"Enter value for {key} ({comment})\n default=`{default}`: ")
    value = response.strip() or default
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


def get_env_value(key: str, default: str = KeyError):
    """
    Get a specific env value by name.
    If no default is given and the key is not found, a KeyError is raised.
    """
    env = read_dotenv()
    if key in env:
        return env[key]
    elif default is KeyError:
        # sourcery skip: compare-via-equals
        raise KeyError(key)

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


def write_content_to_toml_file(content_key: str, content: str, filename=DEFAULT_TOML_NAME):
    if not content:
        return

    filepath = Path(filename)

    config_toml_file = tomlkit.loads(filepath.read_text())
    config_toml_file["services"][content_key] = content

    filepath.write_text(tomlkit.dumps(config_toml_file))


def get_content_from_toml_file(
    services: list[str],
    toml_contents: dict[str, typing.Any],
    content_key: str,
    content: str,
    default: typing.Container[str] | str,
    overwrite: bool = False,
):
    """
    Gets content from a TOML file.

    :param services: A list of services.
    :param toml_contents: A dictionary representing the TOML file.
    :param content_key: The key to look for in the TOML file.
    :param content: The content to display to the user.
    :param default: The default value to return if the conditions are not met.
    :param overwrite: don't skip if key already exists

    :return: The content from the TOML file or the default value.
    :rtype: Any
    """

    has_existing_value = "services" in toml_contents and content_key in toml_contents["services"]

    if has_existing_value and not overwrite:
        print("skipping", content_key)
        return ""

    selected = set()
    if has_existing_value:
        selected.update(toml_contents["services"][content_key])

    return interactive_selected_checkbox_values(services, content, selected=selected) or default


def setup_config_file(filename=DEFAULT_TOML_NAME):
    """
    sets up config.toml for use
    """
    filepath = Path(filename)

    config_toml_file = tomlkit.loads(filepath.read_text())
    if "services" not in config_toml_file:
        filepath.write_text("\n[services]\n")


def write_user_input_to_config_toml(all_services: list[str], filename=DEFAULT_TOML_NAME, overwrite: bool = False):
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

    config_toml_file = tomlkit.loads(filepath.read_text())

    # get chosen services for minimal and logs
    minimal_services = (
        services_no_celery
        if config_toml_file["services"]["services"] == "discover"
        else config_toml_file["services"]["services"]
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

    return TomlConfig.load(filename, cache=False)


def load_dockercompose_with_includes(c: Context = None, dc_path: str | Path = "docker-compose.yml") -> dict:
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

    processed_config = c.run(f"{DOCKER_COMPOSE} -f {dc_path} config", hide=True).stdout.strip()
    # mimic a file to load the yaml from
    return yaml.safe_load(io.StringIO(processed_config))


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
    if c.run("sudo --non-interactive echo ''", warn=True, hide=True).ok:
        # prima
        return True

    sudo_pass = getpass("Please enter the sudo password: ")
    c.config.sudo.password = sudo_pass

    try:
        c.sudo("echo ''", warn=True, hide=True)
        cprint("Sudo password accepted!", color="green", file=sys.stderr)
        return True
    except invoke.exceptions.AuthFailure as e:
        cprint(str(e), color="red", file=sys.stderr)
        return False


def build_toml(c: Context, overwrite: bool = False) -> TomlConfig | None:
    try:
        docker_compose = load_dockercompose_with_includes(c)
    except FileNotFoundError:
        cprint("docker-compose.yml file is missing, setup could not be completed!", color="red")
        return None

    services: dict[str, typing.Any] = docker_compose["services"]
    return write_user_input_to_config_toml(list(services.keys()), overwrite=overwrite)


@task(
    pre=[require_sudo],
    help={
        "run_local_setup": "executes local_tasks setup (default is True)",
        "new_config_toml": "will REMOVE and create a new config.toml file",
    },
)
def setup(c: Context, run_local_setup=True, new_config_toml=False, _retry=False):
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


@task()
def search_adjacent_setting(c, key, silent=False):
    """
    Search for key in all ../*/.env files.
    """
    c: Context
    key: str = key.upper()
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


def next_value(c: Context, key: list[str] | str, lowest: int, silent=True) -> int:
    """Find all other project settings using key, adding 1 to max of all values, or defaults to lowest.

    next_value(c, 'REDIS_PORT', 6379) -> might result 6379, or 6381 if this is the third project to be initialised
    next_value(c, ['PGPOOL_PORT','POSTGRES_PORT','PGBOUNCER_PORT'], 5432) -> finds the next port searching for all keys.
    """
    keys = [key] if isinstance(key, str) else key
    all_settings = {}
    for key in keys:
        settings = search_adjacent_setting(c, key, silent)
        all_settings |= {f"{k}/{key}": v for k, v in settings.items() if v}
        if not silent:
            print()
    values = {int(v) for v in all_settings.values() if v}
    return max(values) + 1 if any(values) else lowest


THREE_WEEKS = 60 * 24 * 7 * 3


@task
def clean_old_sessions(c: Context, relative_glob="web2py/apps/*/sessions", minutes: int = THREE_WEEKS):
    for directory in Path.cwd().glob(relative_glob):
        c.sudo(f'find "{directory}" -type f -mmin +{minutes} -exec rm -f "{{}}" +;')
        remove_empty_dirs(c, directory)


@task
def remove_empty_dirs(c: Context, path: str | Path):
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
def generate_password(_, silent=False):
    """Generate a diceware password using --dice 6."""
    return _generate_password(silent=silent)


def fuzzy_match(val1: str, val2: str, verbose=False) -> float:
    """
    Get the similarity score between two values.

    Used by `edwh settings -f ...` when no exact match was found.
    """
    similarity = fuzz.partial_ratio(val1, val2)
    if verbose:
        print(f"similarity of {val1} and {val2} is {similarity}", file=sys.stderr)
    return similarity


def _settings(find: typing.Optional[str], fuzz_threshold: int = 75):
    all_settings = read_dotenv().items()
    if find is None:
        # don't loop
        return all_settings
    else:
        find = find.upper()
        # if nothing found exactly, try again but fuzzy (could be slower)
        return [(k, v) for k, v in all_settings if find in k.upper() or find in v.upper()] or [
            (k, v) for k, v in all_settings if fuzzy_match(k.upper(), find) > fuzz_threshold
        ]


# noinspection PyUnusedLocal
@task(
    help=dict(find="search for this specific setting", as_json="output as json dictionary"),
    flags={
        "as_json": ["j", "json", "as-json"],
        "fuzz_threshold": ["t", "fuzz-threshold"],
    },
)
def settings(_, find=None, fuzz_threshold=75, as_json=False):
    """
    Show all settings in .env file or search for a specific setting using -f/--find.
    """
    rows = _settings(find, fuzz_threshold)
    if as_json:
        print(json.dumps(dict(rows), indent=3))
    else:
        print(tabulate.tabulate(rows, headers=["Setting", "Value"]))


def show_related_settings(ctx: Context, services: list[str]):
    config = dc_config(ctx)

    rows = {}
    for service in services:
        if service_settings := _settings(service):
            rows |= service_settings
        else:
            with contextlib.suppress(TypeError, KeyError):
                rows |= config["services"][service]["environment"]

    print(tabulate.tabulate(rows.items(), headers=["Setting", "Value"]))


@task(aliases=("volume",))
def volumes(ctx):
    """
    Show container and volume names.

    Based on `docker-compose ps -q` ids and `docker inspect` output.
    """
    lines = []
    for container_id in ctx.run(f"{DOCKER_COMPOSE} ps -q", hide=True, warn=True).stdout.strip().split("\n"):
        ran = ctx.run(f"docker inspect {container_id}", hide=True, warn=True)
        if ran.ok:
            info = json.loads(ran.stdout)
            container = info[0]["Name"]
            lines.extend(
                dict(container=container, volume=volume)
                for volume in [_["Name"] for _ in info[0]["Mounts"] if _["Type"] == "volume"]
            )
        else:
            print(ran.stderr)

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
        "tail": ["tail", "l", "logs"],  # instead of -a
    },
)
def up(
    ctx: Context,
    service: Optional[list[str]] = None,
    build=False,
    quickest=False,
    stop_timeout=2,
    tail=False,
    clean=False,
    show_settings=True,
):
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


def shorten(text: str, max_chars: int) -> str:
    # textwrap looks at words and stuff, not relevant for commands!
    if len(text) <= max_chars:
        return text
    else:
        return f"{text[:max_chars]}..."


@task(
    iterable=["service", "columns"],
    help=dict(
        service="Service to query, can be used multiple times, handles wildcards.",
        quiet="Only show container ids. Useful for scripting.",
        columns="Which columns to display?",
        full_command="Don't truncate the command.",
    ),
)
def ps(ctx, quiet=False, service=None, columns=None, full_command=False):
    """
    Show process status of services.
    """
    ps_output = ctx.run(
        f'{DOCKER_COMPOSE} ps --format json {"-q" if quiet else ""} {" ".join(service_names(service or []))}',
        warn=True,
        hide=True,
    ).stdout.strip()

    services = []

    # list because it's ordered
    selected_columns = columns or ["Name", "Command", "State", "Ports"]

    for service_json in ps_output.split("\n"):
        if not service_json:
            # empty line
            continue

        service = json.loads(service_json)
        service = {k: v for k, v in service.items() if k in selected_columns}
        if not full_command:
            service["Command"] = shorten(service["Command"], 50)

        service = dict(sorted(service.items(), key=lambda x: selected_columns.index(x[0])))
        services.append(service)

    print(tabulate.tabulate(services, headers="keys"))


@task(
    help=dict(
        quiet="Only show ids (mostly directories). Useful for scripting.",
    ),
)
def ls(ctx, quiet=False):
    """
    List running compose projects.
    """
    ctx.run(f'{DOCKER_COMPOSE} ls {"-q" if quiet else ""}')


@task(
    aliases=("log",),
    iterable=["service"],
    help={
        "service": "What services to follow. Defaults to all, can be applied multiple times. ",
        "all": "Ignore --service and show all service logs (same as `-s '*'`).",
        "follow": "Keep scrolling with the output.",
        "debug": "Add timestamps",
        "tail": "Start with how many lines of history.",
        "sort": "Sort the output by timestamp: forced timestamp and mutual exclusive with follow.",
        "ycecream": "Filter on entries with y|",
        "errors": "Filter on entries with e|",
    },
)
def logs(
    ctx,
    service: Optional[list[str]] = None,
    follow: bool = True,
    debug: bool = False,
    tail: int = 500,
    sort: bool = False,
    all: bool = False,  # noqa A002
    ycecream: bool = False,
    errors: bool = False,
    verbose: bool = False,
):
    """Smart docker logging"""
    cmdline = [f"{DOCKER_COMPOSE} logs", f"--tail={tail}"]
    if sort or debug:
        # add timestamps
        cmdline.append("-t")

    if all:
        # -s "*" is the same but `-s *` triggers bash expansion so that's annoying.
        cmdline.extend(service_names([], default="all"))
    else:
        cmdline.extend(service_names(service, default="logs"))

    if sort:
        cmdline.append(r'| sed -E "s/^([^|]*)\|([^Z]*Z)(.*)$/\2|\1|\3/" | sort')
    elif follow:
        # only allow follow is not sorting
        cmdline.insert(2, "-f")

    if ycecream or errors:
        target = []
        if ycecream:
            target.append("y")
        if errors:
            target.append("e")

        target = "|".join(target)
        cmdline.append(f"| grep -E ' ({target})\\|.+' --color=never")
        # catch y| and/or e|
        # -> grep -E ' (y|e)|\.+'

    ctx.run(" ".join(cmdline), echo=verbose, pty=True)


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
)
def stop(ctx, service=None):
    """
    Stops services using docker-compose stop.
    """
    service = service_names(service or [])
    ctx.run(f"{DOCKER_COMPOSE} stop {' '.join(service)}")


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
)
def down(ctx, service=None):
    """
    Stops services using docker-compose down.
    """
    service = service_names(service or []) if service else []

    ctx.run(f"{DOCKER_COMPOSE} down {' '.join(service)}", hide="err")


@task()
def upgrade(ctx, build=False):
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
def build(ctx, yes=False, skip_compile=False):
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

    if not reqs:
        cprint("No .in files found to compile!", "yellow")
    elif with_compile:
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
    ctx,
    service=None,
    force_rebuild=False,
):
    """
    Downs ALL services, then rebuilds services using docker-compose build.
    """
    if service is None:
        service = []

    ctx.run(f"{DOCKER_COMPOSE} down")
    services = service_names(service)

    cache_flag = "--no-cache" if force_rebuild else ""
    services_str = " ".join(services)
    ctx.run(f"{DOCKER_COMPOSE} build {cache_flag} {services_str}")


@task()
def docs(ctx, reinstall=False):
    """
    Local hosted mkdocs documentation.

    Installs mkdocs if unavailable.
    """
    if reinstall:
        print("Installing mkdocs and dependencies...")
        ok = True
        ctx.run("pipx uninstall mkdocs", hide=True, warn=True)
        ok &= ctx.run("pipx install mkdocs", hide=True, warn=True).ok
        ok &= ctx.run(
            "pipx inject mkdocs mkdocs-material plantuml-markdown",
            hide=True,
            warn=True,
        ).ok
        print("result:", ok)
        return ok
    else:
        if not ctx.run("mkdocs serve", warn=True).ok and docs(ctx, reinstall=True):
            docs(ctx)


# noinspection PyUnusedLocal
@task()
def zen(_):
    """Prints the Zen of Python"""
    # noinspection PyUnresolvedReferences
    import this  # noqa


@task()
def whoami(ctx):
    """
    Debug method to determine user and host name.
    """
    i_am = ctx.run("whoami", hide=True).stdout.strip()
    my_location = ctx.run("hostname", hide=True).stdout.strip()
    print(f"{i_am} @ {my_location}")


@task()
def completions(_):
    """
    Prints the script to enable shell completions.
    """
    print("Put this in your .bashrc:")
    print("---")
    print('eval "$(edwh --print-completion-script bash)"')
    print("---")


@task()
def version(ctx):
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

    if ns := collection.collections.get(about):
        ns: invoke.Collection
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
    ctx, du=False, exposes=False, ports=False, host_labels=True, short=False, show_settings=False, as_json=False
):
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


@task
def ew_self_update(ctx: Context):
    """Update edwh to the latest version."""
    ctx.run("~/.local/bin/edwh self-update")
    ctx.run("~/.local/bin/edwh self-update")


@task()
def migrate(ctx: Context):
    up(ctx, service=["migrate"], tail=True)


def find_container_id(ctx: Context, container: str) -> Optional[str]:
    return ctx.run(f"{DOCKER_COMPOSE} ps -aq {container}", hide=True, warn=True).stdout.strip()


def find_container_ids(ctx: Context, *containers: str) -> dict[str, Optional[str]]:
    return {container: find_container_id(ctx, container) for container in containers}


def stop_remove_container(ctx: Context, container_name: str):
    return ctx.run(f"{DOCKER_COMPOSE} rm -vf --stop {container_name}", warn=True)


def stop_remove_containers(ctx: Context, *container_names: str):
    return [stop_remove_container(ctx, _) for _ in container_names]


@task
def clean_redis(_, db_count: int = 3):
    import redis as r

    env = read_dotenv(Path(".env"))
    for db in range(db_count):
        redis_client = r.Redis("localhost", int(env["REDIS_PORT"]), db)
        print(f"Removing {len(redis_client.keys())} keys")
        for key in redis_client:
            del redis_client[key]
        redis_client.close()


@task()
def clean_postgres(ctx):
    # assumes pgpool with pg-0, pg-1 and optionally pg-stats right now!
    confirm(
        "Are you sure you want to wipe the database? This can not be undone [yes,NO]",
        allowed={"yes"},  # strict yes, not just y !!!
        strict=True,  # raises RuntimeError
    )

    # clear backend flag files
    flag_dir = pathlib.Path("migrate/flags")

    for flag_file in flag_dir.glob("*.complete"):
        print("removing", flag_file)
        flag_file.unlink()

    # find the images based on the instances
    pg_data_volumes = []
    for container_name, container_id in find_container_ids(ctx, "pg-0", "pg-1", "pg-stats").items():
        if not container_id:
            # probably missing (such as pg-1, pg-stats in some environments)
            continue

        ran = ctx.run(f"docker inspect {container_id}", hide=True, warn=True)
        if ran.ok:
            info = json.loads(ran.stdout)
            pg_data_volumes.extend([_["Name"] for _ in info[0]["Mounts"]])
        else:
            print(ran.stderr)
            raise EnvironmentError(f"docker inspect {container_id} failed")

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
    clean_all=False,
    db=False,
    postgres=False,
    redis=False,
):
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
        clean_postgres(ctx)

    if clean_all or redis:
        clean_redis(ctx)


@task(aliases=("whipe-db",), flags={"clean_all": ["all", "a"]})
def wipe_db(ctx: Context, clean_all: bool = False, flag_path: str = "migrate/flags", database="pgpool"):
    # 1 + 2. just 'create' without starting anything:
    ctx.run(f"{DOCKER_COMPOSE} create")

    # 3. start cleaning up
    for p in Path(flag_path).glob("migrate-*.complete"):
        p.unlink()

    clean(ctx, db=True, clean_all=clean_all)
    down(ctx)  # remove old containers too

    # 4. start the database
    up(ctx, service=[database], show_settings=False)
    # 5. start migrations (incl. backup recovery)
    up(ctx, service=["migrate"], tail=True, show_settings=False)
    # 6. fully start normal services:
    up(ctx)


@task
def show_config(_: Context):
    """
    Show the current values from .toml after loading.
    """
    config = TomlConfig.load()
    cprint(f"TomlConfig: {json.dumps(config.__dict__, default=str, indent=2) if config else 'None'}")


@task
def change_config(c: Context):
    """
    Change the settings in .toml
    """
    build_toml(c, overwrite=True)


@task
def debug(_):
    print(get_env_value("IS_DEBUG", "0"))


@task(aliases=("ew",))
def edwh(_):
    print("Hehe you silly goose", file=sys.stderr)
