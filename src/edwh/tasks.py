import diceware
import invoke

try:
    import glob
    import csv
    import shlex
    import datetime
    import io
    import os
    import pathlib
    import random
    import re
    import sys
    import time
    import typing
    import json
    import importlib.util
    from collections import defaultdict, OrderedDict
    from dataclasses import dataclass, field
    from pathlib import Path
    from statistics import median

    import tabulate
    import warnings
    import yaml
    from invoke import task, Result, Context

    if sys.version_info > (3, 11):
        import tomllib
    else:
        import tomlkit

except ImportError as e:
    if sys.argv[0].split("/")[-1] in ("inv", "invoke"):
        print("WARNING: this tasks.py works best using the edwh command instead of using inv[oke] directly.\n")
    print("ImportError:", e)
    exit(1)


def load_toml(file: Path) -> dict:
    """
    Depends on Python version
    """
    with file.open() as f:
        contents = f.read()
        if sys.version_info > (3, 11):
            return tomllib.loads(contents)
        else:
            return tomlkit.parse(contents)


def confirm(prompt: str, default=False) -> bool:
    allowed = {"y", "1"}
    if default:
        allowed.add(" ")

    answer = input(prompt).lower().strip()
    answer += " "

    return answer[0] in allowed


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
        if not os.path.isfile(config_path):
            setup(invoke.Context())
        config = load_toml(config_path)

        if "services" not in config:
            setup(invoke.Context())
        for key in config["services"].keys():
            if key not in ["minimal", "services", "include_celeries_in_minimal", "log"]:
                setup(invoke.Context())

        if config["services"]["services"] == "discover":
            with open("docker-compose.yml", "r") as compose:
                compose = yaml.load(compose, yaml.SafeLoader)
                all_services = compose["services"].keys()
        else:
            all_services = config["services"]["services"]

        celeries = [s for s in all_services if "celery" in s.lower()]

        minimal_services = config["services"]["minimal"] + celeries
        if config["services"]["include_celeries_in_minimal"]:
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


def executes_correctly(c: Context, argument: str) -> bool:
    """returns True if the execution was without error level"""
    return c.run(argument, warn=True, hide=True).ok


def execution_fails(c: Context, argument: str) -> bool:
    """Returns true if the execution fails based on error level"""
    return not executes_correctly(c, argument)


_dotenv_settings = {}


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
    if key not in env:
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
    else:
        return env[key]


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
        outlines.append(f"{target.strip().upper()}={str(value).strip()}")
    with path.open(mode="w") as env_file:
        env_file.write("\n".join(outlines))
        env_file.write("\n")


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


def exec_setup_in_other_task(c, run_setup):
    """
    Run a setup function in another task.py.
    """
    # execute local_tasks setup
    old_path = sys.path[:]

    for path in ['.', '..', '../..']:
        path = pathlib.Path(path)
        sys.path = [str(path)] + old_path
        try:
            import tasks as local_tasks

            try:
                if run_setup:
                    local_tasks.setup(c)
            except:
                print(
                    "the setup in you're local tasks.py crashed, to not run the setup please give up the argument "
                    "--no-run-setup"
                )
                print("the setup in you're local tasks.py crashed, to not run the setup please give up the argument "
                      "--no-run-local-setup")
                raise
            break
        except ImportError:
            continue

    sys.path = old_path


def print_services(c, services, selected_services=None, warn: str = None):
    """
    print all the services that are in the docker-compose.yml

    :param services: docker services that are in the docker-compose.yml
    :return: a list of all services in the docker-compose.yml
    """
    c.run("clear")
    if warn is not None:
        print(warn)

    print("\nservices:")
    for index in range(len(services)):
        if services[index] == "":
            continue
        print(f"{index + 1}: {services[index]}")
    print("Press enter when you're done.\n")

    if selected_services is None:
        return

    print("selected services:")
    for index in range(len(selected_services)):
        print(f"{index + 1}:", selected_services[index])


def get_services_from_user(c, services: list, input_string: str, warn: str = None):
    """
    gets the input from the user and writes it to a string

    :param services: docker services that are in the docker-compose.yml
    :param input_string: string that the user will see when choosing dockers
    :param warn: prints an warning message if set
    :return: services that are chosen by the user
    """
    print_services(c, services, warn=warn)
    chosen_services = []

    while (chosen_id := input(input_string)) != "":
        chosen_ids = str(chosen_id).split(",")
        chosen_services.extend(f'{services[int(cid) - 1]}' for cid in chosen_ids
                               if int(cid) - 1 < len(services) and
                               services[int(cid) - 1] not in chosen_services)

        print_services(c, services, chosen_services)
    return chosen_services


def write_user_input_to_config_toml(c, services: list):
    """
    write chosen user dockers to config.toml


    :param services: list of all docker services that are in the docker-compose.yml
    :return:
    """

    doc = tomlkit.loads(Path("config.toml").read_text())

    config_content = tomlkit.table()
    warn = None
    if "[services]" in tomlkit.dumps(doc):
        now = datetime.datetime.now()
        new_services_name = f"[services{now.strftime('%d-%m-%Y-%H-%M-%S')}]"
        doc = tomlkit.loads(tomlkit.dumps(doc).replace("[services]", new_services_name))

        warn = "\033[93m" + "[services] has been found in the existing config.toml, changing [services] to " + \
               f"{new_services_name} \033[0m"

    # let user choose services
    chosen_services = get_services_from_user(c, services, "select a service by number(default is 'discover'): ", warn)

    config_content.add("services", chosen_services if len(chosen_services) != 0 else 'discover')

    # services you can choose from by minimal and logs
    if len(chosen_services) != 0:
        services_to_choose_from = chosen_services
    else:
        services_to_choose_from = services

    # get chosen services from user
    chosen_minimal_services = get_services_from_user(c, services_to_choose_from, "select minimal services by number: ")

    config_content.add("minimal", chosen_minimal_services)

    c.run("clear")
    # check if user wants to include celeries
    include_celeries = "true" if input("do you want to include celeries(Y/n): ").replace(" ", "") \
                                 in ["", "y", "Y"] else "false"

    config_content.add("include_celeries_in_minimal", include_celeries)

    chosen_log_services = get_services_from_user(c, services_to_choose_from,
                                                 "select services to be logged by number: ")

    config_content.add("log", chosen_log_services)

    doc.add("services", config_content)

    with open("config.toml", "w") as config_file:
        config_file.write(tomlkit.dumps(doc))


@task(help={'run_local_setup': "executes local_tasks setup(default is True)"})
def setup(c, run_local_setup=True):
    """
    sets up config.toml and tries to run setup in local tasks.py if it exists

    while configuring the config.toml the program will ask you to select a service by id.
    All service can be found by the print that is done above.
    While giving up id's please only give 1 id at the time, this goes for the services and the minimal services

    """
    c.run("clear")
    # create config file
    if not Path.is_file(Path("config.toml")):
        with open("config.toml", "x") as config_toml:
            config_toml.close()
    else:
        continue_setup = input("would you like to config the config.toml(Y/n): ").replace(" ", "")
        if continue_setup not in ["", "y", "Y"]:
            exec_setup_in_other_task(c, run_local_setup)
            sys.exit(255)

    print("getting services...")

    # get and print all found docker compose services
    services = c.run("docker-compose config --services", hide=True).stdout.split("\n")
    c.run("clear")
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


@task(aliases=tuple(["volume"]))
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
            for volume in [_["Name"] for _ in info[0]["Mounts"] if _["Type"] == "volume"]:
                lines.append(dict(container=container, volume=volume))
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
            "docker-compose run --rm migrate invoke -r /shared_code/edwh/core/backend -c support update-opengraph"
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
    aliases=tuple(["log"]),
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
        cmdline.append(f"-t")
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
        if not ctx.run("mkdocs serve", warn=True).ok:
            if docs(ctx, reinstall=True):
                docs(ctx)


# noinspection PyUnusedLocal
@task()
def zen(ctx):
    """Prints the Zen of Python"""
    # noinspection PyUnresolvedReferences
    import this


@task
def whoami(ctx):
    print(ctx.run("whoami", hide=True).stdout, "@", ctx.run("hostname", hide=True).stdout)
