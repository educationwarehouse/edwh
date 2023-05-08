import json
import os
import pathlib
import re
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path

import requests
from packaging.version import parse as parse_package_version, InvalidVersion, Version

import diceware
import invoke
import tabulate
import tomlkit  # can be replaced with tomllib when 3.10 is deprecated
import yaml
from invoke import task, Context
from termcolor import colored

# noinspection PyUnresolvedReferences
# ^ keep imports for backwards compatibility (e.g. `from edwh.tasks import executes_correctly`)
from .helpers import confirm, execution_fails, executes_correctly


def service_names(service_arg: list[str]) -> list[str]:
    """
    Returns a list of matching servicenames based on ALL_SERVICES. filename globbing is applied.

    Use service_names(['*celery*','pg*']) to select all celery services, and all of pg related instances.
    :param service_arg: list of services or service selectors using wildcards
    :type service_arg: list of strings
    :return: list of unique services names that match the given list
    :rtype: list of string
    """
    import fnmatch

    config = TomlConfig.load()
    selected = set()
    for service in service_arg:
        selected.update(fnmatch.filter(config.all_services, service))

    if service_arg and not selected:
        # when no service matches the name, don't return an empty list, as that would `up` all services
        # instead of the wanted list. This includes typos, where a single typo could cause all services to be started.
        print(f"ERROR: No services found matching: {service_arg!r}")
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


def exec_setup_in_other_task(c: Context, run_setup: bool):
    """
    Run a setup function in another task.py.
    """
    # execute local_tasks setup
    old_path = sys.path[:]

    path = pathlib.Path(".").absolute()
    while path != path.parent:
        sys.path = [str(path)] + old_path

        path = path.parent.absolute()  # before anything that can crash, to prevent infinite loop!
        try:
            import tasks as local_tasks

            if run_setup:
                try:
                    local_tasks.setup(c)
                    break
                except AttributeError:
                    if hasattr(local_tasks, "setup"):
                        # reraise because we can't handle it here, and the user should be informed fully
                        raise

                    print(
                        "No setup function found in your nearest tasks.py",
                        local_tasks,
                    )
                    break
            del local_tasks
        except ImportError:
            # silence this error, if the import cannot be performed, that's not a problem
            if os.path.exists("tasks.py"):
                print(f"Could not import tasks.py from {path}")
                raise
            else:
                continue
        finally:
            sys.path = old_path


_dotenv_settings = {}


def _apply_env_vars_to_template(source_lines: list[str], env: dict) -> list[str]:
    needle = re.compile(r'# *template:')

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
        indention = (re.findall(r'^[\s]*', old) + [''])[0]
        if not old.lstrip().startswith('#'):
            # skip comment only lines
            new = template.format(**env)
            # reconstruct the line for the yaml file
            line = f'{indention}{new} # template: {template}'
        new_lines.append(line)
    return new_lines


# used for treafik config
def apply_dotenv_vars_to_yaml_templates(yaml_path: Path, dotenv_path: Path):
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
    with yaml_path.open(mode='r+') as yaml_file:
        source_lines = yaml_file.read().split('\n')
        new_lines = _apply_env_vars_to_template(source_lines, env)
        # move filepointer to the start of the file
        yaml_file.seek(0, 0)
        # write all lines and newlines to the file
        yaml_file.write('\n'.join(new_lines))
        # and remove any part that might be left over (when the new file is shorter than the old one)
        yaml_file.truncate()


@dataclass
class TomlConfig:
    config: dict
    all_services: list[str]
    celeries: list[str]
    services_minimal: list[str]
    services_log: list[str]
    dotenv_path: Path
    __loaded: "TomlConfig" = field(init=False, default=None)  # cache using class instance singleton

    @classmethod
    def load(cls, fname="config.toml"):
        """
        Load config toml file, raising an error if it does not exist.

        Since this file should be in .git error suppression is not needed.
        Returns a dictionary with CONFIG, ALL_SERVICES, CELERIES and MINIMAL_SERVICES
        """
        if TomlConfig.__loaded:
            return TomlConfig.__loaded

        config_path = Path(fname)
        if not pathlib.Path.exists(config_path):
            setup(invoke.Context())

        with config_path.open() as f:
            config = tomlkit.load(f)

        if "services" not in config:
            setup(invoke.Context())
        for service_name in ["minimal", "services", "include_celeries_in_minimal", "log"]:
            if service_name not in config["services"].keys():
                setup(invoke.Context())

        if config["services"]["services"] == "discover":
            with open("docker-compose.yml", "r") as compose:
                compose = yaml.load(compose, yaml.SafeLoader)
                all_services = compose["services"].keys()
        else:
            all_services = config["services"]["services"]

        celeries = [s for s in all_services if "celery" in s.lower()]

        minimal_services = config["services"]["minimal"]
        if config["services"]["include_celeries_in_minimal"] == "true":
            minimal_services += celeries
        cls.__loaded = TomlConfig(
            config=config,
            all_services=all_services,
            celeries=celeries,
            services_minimal=minimal_services,
            services_log=config["services"]["log"],
            dotenv_path=Path(config.get("dotenv", {}).get("path", ".env")),
        )
        return cls.__loaded


def read_dotenv(env_path: Path = None) -> dict:
    """
    Read .env file from env_path and return a dict of key/value pairs.

    If env_path is not given, TomlConfig.load().dotenv_path is used.

    :param env_path: optional path to .env file
    :return: dict of key/value pairs from the .env file
    """
    cache_key = str(env_path) if env_path else "."
    if existing := _dotenv_settings.get(cache_key):
        # 'cache'
        return existing

    items = {}
    config = TomlConfig.load()
    with (env_path or config.dotenv_path).open(mode="r") as env_file:
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

    _dotenv_settings[cache_key] = items
    return items


def check_env(
    key: str,
    default: typing.Optional[str],
    comment: str,
    prefix: str | None = None,
    postfix: str | None = None,
):
    """
    Test if key is in .env file path, appends prompted or default value if missing.
    """
    config = TomlConfig.load()
    env = read_dotenv()
    if key in env:
        return env[key]

    with config.dotenv_path.open(mode="r+") as env_file:
        response = input(f"Enter value for {key} ({comment})\n default=`{default}`: ")
        value = response.strip() or default
        if prefix:
            value = prefix + value
        if postfix:
            value += postfix
        env_file.seek(0, 2)
        env_file.write(f"\n{key.upper()}={value}\n")

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
    """update/set environment variables in the .env file, keeping comments intact

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


def print_services(services: list, selected_services: list = None, warn: str = None):
    """
    print all the services that are in the docker-compose.yml

    :param services: docker services that are in the docker-compose.yml
    :return: a list of all services in the docker-compose.yml
    """
    if warn is not None:
        print(warn)

    print("\nservices:")
    for index in range(len(services)):
        if services[index] == "":
            continue
        print(f"{index + 1}: {services[index]}")

    if selected_services is None:
        return

    print("\nselected services:")
    for index in range(len(selected_services)):
        print(f"{index + 1}:", selected_services[index])


def write_content_to_toml_file(content_key: str, content: str, filename="config.toml"):
    if not content:
        return

    config_toml_file = tomlkit.loads(Path(filename).read_text())
    config_toml_file["services"][content_key] = content

    with open("config.toml", "w") as config_file:
        config_file.write(tomlkit.dumps(config_toml_file))
        config_file.close()


def get_content_from_toml_file(services: list, toml_contents: dict, content_key: str, content: str, default: str):
    """
    Gets content from a TOML file.

    :param services: A list of services.
    :param toml_contents: A dictionary representing the TOML file.
    :param content_key: The key to look for in the TOML file.
    :param content: The content to display to the user.
    :param default: The default value to return if the conditions are not met.
    :return: The content from the TOML file or the default value.
    :rtype: Any
    """

    if "services" in toml_contents and content_key in toml_contents["services"]:
        return ""

    print_services(services)
    print(
        colored(
            "NOTE: To select multiple services please use single spaces or ',' inbetween numbers\n"
            "For example '1, 2, 3, 4'",
            'green',
        )
    )
    if content_key == "services":
        print(colored("discover will include all services.\n", "green"))
    chosen_services_ids = input(content)
    if "," not in chosen_services_ids:
        chosen_services_ids = chosen_services_ids.split(" ")
    else:
        chosen_services_ids = chosen_services_ids.replace(" ", "").split(",")

    if chosen_services_ids[0] in default or len(chosen_services_ids[0]) == 0:
        return default

    return [services[int(service_id) - 1] for service_id in chosen_services_ids]


def setup_config_file(filename="config.toml"):
    """
    sets up config.toml for use
    """
    config_toml_file = tomlkit.loads(Path(filename).read_text())
    if "services" not in config_toml_file:
        with open(filename, "w") as config_file:
            config_file.write("\n[services]\n")
            config_file.close()


def write_user_input_to_config_toml(c, all_services: list):
    """
    write chosen user dockers to config.toml


    :param services: list of all docker services that are in the docker-compose.yml
    :return:

    """
    setup_config_file()
    config_toml_file = tomlkit.loads(Path("config.toml").read_text())

    # services
    services_list = get_content_from_toml_file(
        all_services,
        config_toml_file,
        "services",
        "select a service by number(default is 'discover'): ",
        "discover",
    )
    write_content_to_toml_file("services", services_list)

    config_toml_file = tomlkit.loads(Path("config.toml").read_text())

    # get chosen services for minimal and logs
    minimal_services = (
        all_services
        if config_toml_file["services"]["services"] == "discover"
        else config_toml_file["services"]["services"]
    )

    # services
    content = get_content_from_toml_file(
        minimal_services,
        config_toml_file,
        "minimal",
        "select minimal services by number: ",
        [],
    )
    write_content_to_toml_file("minimal", content)

    # check if minimal exists if yes add celeries to services
    if "services" not in config_toml_file or "include_celeries_in_minimal" not in config_toml_file["services"]:
        # check if user wants to include celeries
        include_celeries = (
            "true"
            if input("do you want to include celeries in minimal(Y/n): ").replace(" ", "") in ["", "y", "Y"]
            else "false"
        )
        write_content_to_toml_file("include_celeries_in_minimal", include_celeries)

    content = get_content_from_toml_file(
        minimal_services,
        config_toml_file,
        "log",
        "select services to be logged by number: ",
        [],
    )
    write_content_to_toml_file("log", content)


@task(
    help={
        "run_local_setup": "executes local_tasks setup(default is True)",
        "new_config_toml": "will REMOVE and create a new config.toml file",
    }
)
def setup(c, run_local_setup=True, new_config_toml=False):
    """
    sets up config.toml and tries to run setup in local tasks.py if it exists

    while configuring the config.toml the program will ask you to select a service by id.
    All service can be found by the print that is done above.
    While giving up id's please only give 1 id at the time, this goes for the services and the minimal services

    """

    if new_config_toml and Path.is_file(Path("config.toml")):
        remove_config = input(colored("are you sure you want to remove the config.toml(y/N): ", "red"))
        if remove_config.replace(" ", "") in ["y", "Y"]:
            os.remove("config.toml")

    if not Path.is_file(Path("config.toml")):
        with open("config.toml", "x") as config_toml:
            config_toml.close()

    print("getting services...")

    # get and print all found docker compose services
    services = c.run("docker-compose config --services", hide=True).stdout.split("\n")
    write_user_input_to_config_toml(c, services)
    exec_setup_in_other_task(c, run_local_setup)


@task()
def search_adjacent_setting(c, key, silent=False):
    """
    Search for key in all ../*/.env files.
    """
    c: Context
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


def next_value(c, key, lowest):
    """Find all other project settings using key, adding 1 to max of all values, or defaults to lowest.

    next_value(c, 'REDIS_PORT', 6379) -> might result 6379, or 6381 if this is the third project to be initialised
    """
    settings = search_adjacent_setting(c, key)
    values = {int(v) for v in settings.values() if v}
    return max(values) + 1 if any(values) else lowest


def set_permissions(c: Context, path, uid=1050, gid=1050, filepermissions=664, directorypermissions=775) -> None:
    # find all directories, print the output, feed those to xargs which converts lines in to arguments to the chmod
    # command.
    c.sudo(f'find "{path}" -type d -print0 | sudo xargs -0 chmod {directorypermissions}')
    # find all files, print the output, feed those to xargs which converts lines in to arguments to the chmod command.
    c.sudo(f'find "{path}" -type f -print0 | sudo xargs -0 chmod {filepermissions}')
    # simply apply new ownership to each and every directory
    c.sudo(f'chown -R {uid}:{gid} "{path}" ')


@task(help=dict(silent="do not echo the password"))
def generate_password(c, silent=False):
    """Generate a diceware password using --dice 6."""
    password = diceware.get_passphrase()
    if not silent:
        print("Password:", password)
    return password


# noinspection PyUnusedLocal
@task(help=dict(find="search for this specific setting"))
def settings(ctx, find=None):
    """
    Show all settings in .env file or search for a specific setting using -f/--find.
    """
    rows = [(k, v) for k, v in read_dotenv().items() if find is None or find.upper() in k.upper() or find in v]
    print(tabulate.tabulate(rows, headers=["Setting", "Value"]))


@task(aliases=("volume",))
def volumes(ctx):
    """
    Show container and volume names.

    Based on `docker-compose ps -q` ids and `docker inspect` output.
    """
    lines = []
    for container_id in ctx.run("docker-compose ps -q", hide=True, warn=True).stdout.strip().split("\n"):
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
        service="Service to up, defaults to config.toml's [services].minimal. "
                "Can be used multiple times, handles wildcards.",
        build="request a build be performed first",
        quickest="restart only, no down;up",
        stop_timeout="timeout for stopping services, defaults to 2 seconds",
        tail="tails the log of restart services, defaults to False",
        clean="adds `--renew-anon-volumes --build` to `docker-compose up` command ",
    ),
    iterable=["service"],
)
def up(
    ctx,
    service=None,
    build=False,
    quickest=False,
    stop_timeout=2,
    tail=False,
    clean=False,
):
    """Restart (or down;up) some or all services, after an optional rebuild."""
    ctx: Context = ctx
    config = TomlConfig.load()
    # recalculate the hash and save it, so with the next up, migrate will see differences and start migration
    set_env_value(config.dotenv_path, "SCHEMA_VERSION", calculate_schema_hash())
    # test for --service arguments, if none given: use defaults
    services = service_names(service or config.services_minimal)
    services_ls = " ".join(services)

    if build:
        ctx.run(f"docker-compose build {services_ls}")
    if quickest:
        ctx.run(f"docker-compose restart {services_ls}")
    else:
        ctx.run(f"docker-compose stop -t {stop_timeout}  {services_ls}")
        ctx.run(f"docker-compose up {'--renew-anon-volumes --build' if clean else ''} -d {services_ls}")
    if "py4web" in services_ls:
        ctx.run(
            "docker-compose run --rm migrate invoke -r /shared_code/edwh/core/backend -c support update-opengraph",
            warn=True,
        )
    if tail:
        ctx.run(f"docker-compose logs --tail=10 -f {services_ls}")


@task(
    iterable=["service"],
    help=dict(
        service="Service to query, can be used multiple times, handles wildcards.",
        quiet="Only show container ids. Useful for scripting.",
    ),
)
def ps(ctx, quiet=False, service=None):
    """
    Show process status of services.
    """
    ctx.run(f'docker-compose ps {"-q" if quiet else ""} {" ".join(service_names(service or []))}')


@task(
    aliases=("log",),
    iterable=["service"],
    help={
        "follow": "Keep scrolling with the output.",
        "debug": "Add timestamps",
        "tail": "Start with how many lines of history.",
        "service": "What services to follow. Defaults to all, can be applied multiple times. ",
    },
)
def logs(ctx, follow=True, debug=False, tail=500, service=None):
    """Smart docker logging"""
    cmdline = ["docker-compose logs", f"--tail={tail}"]
    if follow:
        cmdline.append("-f")
    if debug:
        # add timestamps
        cmdline.append("-t")
    if service:
        cmdline.extend(service_names(service))
    ctx.run(" ".join(cmdline))


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
)
def stop(ctx, service=None):
    """
    Stops services using docker-compose stop.
    """
    service = service_names(service or [])
    ctx.run(f"docker-compose stop {' '.join(service)}")


@task(
    iterable=["service"],
    help=dict(service="Service to stop, can be used multiple times, handles wildcards."),
)
def down(ctx, service=None):
    """
    Stops services using docker-compose down.
    """
    service = service_names(service or [])
    ctx.run(f"docker-compose down {' '.join(service)}")


@task(
    help=dict(
        yes="Don't ask for confirmation, just do it. "
            "(unless requirements.in files are found and the `edwh-pipcompile-plugin` is not installed)",
    )
)
def build(ctx, yes=False):
    """
    Build all services.

    Will test for the presence of `edwh-pipcompile-plugin` and use it to compile
    requirements.in files to requirements.txt files in child directories.
    """
    reqs = list(Path(".").rglob("*/requirements.in"))

    try:
        # noinspection PyUnresolvedReferences
        import edwh_pipcompile_plugin as pcl

        with_compile = True
    except ImportError:
        print("`edwh-pipcompile-plugin` not found, unable to compile requirements.in files.")
        print("Install with `pipx inject edwh edwh-pipcompile-plugin`")
        print()
        print("possible files to compile:")
        for req in reqs:
            print("  ", req)
        with_compile = False

    if with_compile:
        for idx, req in enumerate(reqs, 1):
            reqtxt = req.parent / "requirements.txt"
            print(
                f"{idx}/{len(reqs)}: working on {req}",
            )
            if (not reqtxt.exists()) or (reqtxt.stat().st_ctime < req.stat().st_ctime):
                print("outdated" if reqtxt.exists() else "requirements.txt doesn't exist.")
                if yes or confirm(f"recompile {req}? [Yn]", default=True):
                    pcl.compile(ctx, str(req.parent))
            else:
                print("still current")
    else:
        print("Compilation of requirements.in files skipped.")
    if yes or (not with_compile and confirm("Build docker images? [yN]", default=False)):
        ctx.run("docker-compose build")


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
    ctx.run("docker-compose down")
    services = service_names(service)
    ctx.run(f"docker-compose build {'--no-cache' if force_rebuild else ''} " + " ".join(services))


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
def zen(ctx):
    """Prints the Zen of Python"""
    # noinspection PyUnresolvedReferences
    import this


@task
def whoami(ctx):
    i_am = ctx.run("whoami", hide=True).stdout.strip()
    my_location = ctx.run("hostname", hide=True).stdout.strip()
    print(f"{i_am} @ {my_location}")


@task
def completions(ctx):
    print("Put this in your .bashrc:")
    print("---")
    print('eval "$(edwh --print-completion-script bash)"')
    print("---")


PYPI_URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'


def _get_pypi_info(package: str):
    return requests.get(
        PYPI_URL_PATTERN.format(package=package)
    ).json()


def _get_latest_version_from_pypi(package: str):
    data = _get_pypi_info(package)

    return parse_package_version(data["info"]["version"])


def _get_available_plugins_from_pypi(package: str, extra: str = None):
    data = _get_pypi_info(package)
    extras = data["info"]["requires_dist"]

    if extra:
        extras = [_.split(";")[0] for _ in extras if _.endswith(f"; extra == '{extra}'")]

    return list(extras)


def _determine_outdated(installed_plugins: typing.Iterable[str]):
    old_plugins: dict[str, Version] = {}
    for pkg in installed_plugins:
        try:
            if "==" not in pkg:
                raise InvalidVersion

            name, raw_version = pkg.split("==")
            version = parse_package_version(raw_version)

            latest = _get_latest_version_from_pypi(name)

            if version != latest:
                old_plugins[name] = latest

        except InvalidVersion:
            # probably installed locally, skip!
            continue

    return old_plugins


def _plugins(c, pip_command="pip") -> list[str]:
    return c.run(f'{pip_command} freeze | grep edwh', hide=True, warn=True).stdout.strip().split("\n")


def _self_update(c, pip_command="pip"):
    edwh_packages = _plugins(c, pip_command)
    if not edwh_packages or len(edwh_packages) == 1 and edwh_packages[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")

    old_plugins = _determine_outdated(edwh_packages)

    if not old_plugins:
        print("Nothing to update")
        exit()

    print(f"Will try to updated {len(old_plugins)} packages.")

    success = []
    failure = []
    for plugin, version in old_plugins.items():
        result = c.run(f"{pip_command} install {plugin}=={version}", warn=True).stdout

        if f"Successfully installed {plugin}" in result:
            success.append(plugin)
        else:
            failure.append(plugin)

    print(f"{len(success)}/{len(old_plugins)} updated successfully.")
    if failure:
        print(f"{', '.join(failure)} failed updating")


PIP_COMMAND_FOR_PIPX = "pipx runpip edwh"


@task
def plugins(c):
    """
    List installed plugins
    """
    available_plugins = _get_available_plugins_from_pypi('edwh', 'plugins')

    try:
        installed_plugins_raw = _plugins(c)
        pipx_used = False

        if not installed_plugins_raw or len(installed_plugins_raw) == 1 and installed_plugins_raw[0] == "":
            raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")
    except ModuleNotFoundError:
        installed_plugins_raw = _plugins(c, PIP_COMMAND_FOR_PIPX)
        pipx_used = True

    installed_plugins = {_.split(" @ ")[0].split("==")[0] for _ in installed_plugins_raw}
    old_plugins = _determine_outdated(installed_plugins_raw)

    for plugin in available_plugins:
        if plugin in old_plugins:
            print(colored(
                f"• {plugin}",
                'yellow',
            ))
        elif plugin in installed_plugins:
            print(colored(
                f"• {plugin}",
                'green',
            ))
        else:
            print(colored(
                f"◦ {plugin}",
                'red',
            ))

    if old_plugins:
        print()
        cmd = "self-update-pipx" if pipx_used else "self-update"
        s = "" if len(old_plugins) == 1 else "s"
        print(colored(f"{len(old_plugins)} plugin{s} are out of date. Try `edwh {cmd}` to fix this.", "yellow"))


@task
def self_update_pipx(c):
    """
    Updates `edwh` and all plugins.
    Use this only when you installed `edwh` via pipx

    :param c:
    :type c: Context
    :return:
    """
    try:
        _self_update(c, PIP_COMMAND_FOR_PIPX)
    except ModuleNotFoundError:
        print(colored("WARN: No `edwh` modules found. Perhaps you are NOT using pipx? Try ew self-update", "yellow"))
        exit(1)


@task
def self_update(c):
    """
    Updates `edwh` and all plugins.
    Only use this command when using a virtualenv (not pipx!)

    :param c: invoke ctx
    :type c: Context
    :return:
    """
    try:
        _self_update(c, "pip")
    except ModuleNotFoundError:
        print(colored("WARN: No `edwh` modules found. Perhaps you are using pipx? Try ew self-update-pipx", "yellow"))
        exit(1)
