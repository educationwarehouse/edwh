"""
This files contains everything to do with meta-tasks such as plugins
"""

import concurrent.futures
import datetime
import typing

import requests
from invoke import task, Context
from packaging.version import parse as parse_package_version, InvalidVersion, Version
from termcolor import colored

PYPI_URL_PATTERN = 'https://pypi.python.org/pypi/{package}/json'


def _get_pypi_info(package: str) -> dict:
    """
    Load metadata from pypi for a package
    """
    return requests.get(PYPI_URL_PATTERN.format(package=package)).json()


def _get_latest_version_from_pypi(package: str) -> Version:
    """
    Get the latest Version for a package  from pypi
    """
    data = _get_pypi_info(package)

    return parse_package_version(data["info"]["version"])


def _get_available_plugins_from_pypi(package: str, extra: str = None) -> list[str]:
    """
    List all plugins available for package, optionally for a specific 'extra'.

    e.g.
    [mypackage]
    dev = ['package1', 'package2']
    another_extra = ['package1', 'package3']

    > _get_available_plugins_from_pypi('mypackage')
    ['package1', 'package2', 'package3']

    > _get_available_plugins_from_pypi('mypackage, 'dev')
    ['package1', 'package2']

    """
    data = _get_pypi_info(package)
    extras = data["info"]["requires_dist"]

    if extra:
        extras = [_.split(";")[0] for _ in extras if _.endswith(f"; extra == '{extra}'")]

    return list(extras)


def _gather_package_metadata_threaded(packages: typing.Iterable[str]):
    """
    For any package in packages, gather its metadata from pypi
    """
    all_data: dict[str, dict | None] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        pkg_names = [_.split("==")[0] for _ in packages]
        for result, package in zip(executor.map(_get_pypi_info, pkg_names), packages):
            all_data[package] = result

    return all_data


def _determine_outdated_threaded(installed_plugins: typing.Iterable[str]) -> dict[str, Version]:
    """
    Like _determine_outdated but parallelized with Threading

    installed_plugins is a list (or other iterable) of ["name==version", "name @ location"] type strings
    """
    plugins_metadata = _gather_package_metadata_threaded([_ for _ in installed_plugins if " @ " not in _])

    outdated = {}
    for plugin, metadata in plugins_metadata.items():
        try:
            name, current_version = plugin.split("==")
            current_version = parse_package_version(current_version)
            latest_version = parse_package_version(metadata["info"]["version"])
        except:
            # no current or latest version found? skip
            continue

        if current_version and latest_version and latest_version > current_version:
            outdated[name] = latest_version

    return outdated


def _plugins(c: Context, pip_command="pip") -> list[str]:
    """
    List installed edwh-plugins
    """
    return c.run(f'{pip_command} freeze | grep edwh', hide=True, warn=True).stdout.strip().split("\n")


def _self_update(c: Context, pip_command="pip") -> None:
    """
    Update edwh package and all installed extra's
    """
    edwh_packages = _plugins(c, pip_command)
    if not edwh_packages or len(edwh_packages) == 1 and edwh_packages[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")

    old_plugins = _determine_outdated_threaded(edwh_packages)

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


def _parse_versions(installed: list[str]) -> dict[str, Version | None]:
    """
    Given a list of installed packages from pip freeze (_plugins), gather the parsed versions
    """
    versions = {}
    for pkg in installed:
        parts = pkg.split(" @ ")[0].split("==")
        name = parts[0]
        try:
            version = parse_package_version(parts[1])
        except (InvalidVersion, IndexError):
            version = None
        # finally:
        versions[name] = version

    return versions


@task()
def plugins(c):
    """
    List installed plugins

    :param c: invoke ctx
    :type c: Context
    """
    available_plugins = ["edwh"] + _get_available_plugins_from_pypi('edwh', 'plugins')
    try:
        installed_plugins_raw = _plugins(c)
        pipx_used = False

        if not installed_plugins_raw or len(installed_plugins_raw) == 1 and installed_plugins_raw[0] == "":
            raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")
    except ModuleNotFoundError:
        installed_plugins_raw = _plugins(c, PIP_COMMAND_FOR_PIPX)
        pipx_used = True
    installed_plugins = _parse_versions(installed_plugins_raw)

    now = datetime.datetime.now()
    plugin_info = _gather_package_metadata_threaded(installed_plugins.keys())

    old_plugins = []
    for plugin in available_plugins:
        metadata = plugin_info[plugin]
        current_version = installed_plugins[plugin]
        latest_version = parse_package_version(metadata["info"]["version"]) if metadata else None
        if latest_version and current_version:
            is_outdated = latest_version > current_version
        else:
            is_outdated = False

        github_url = metadata["info"]["project_urls"]["Documentation"]

        clean_name = plugin.removeprefix("edwh-").removesuffix("-plugin")
        if is_outdated:
            old_plugins.append(plugin)
            print(
                colored(
                    f"• {clean_name} ({latest_version} > {current_version}) - {github_url}",
                    'yellow',
                )
            )
        elif plugin in installed_plugins:
            print(
                colored(
                    f"• {clean_name} - {github_url}",
                    'green',
                )
            )
        else:
            print(
                colored(
                    f"◦ {clean_name} - {github_url}",
                    'red',
                )
            )

    if old_plugins:
        print()
        cmd = "self-update-pipx" if pipx_used else "self-update"
        s = "" if len(old_plugins) == 1 else "s"
        print(colored(f"{len(old_plugins)} plugin{s} are out of date. Try `edwh {cmd}` to fix this.", "yellow"))


@task()
def self_update_pipx(c):
    """
    Updates `edwh` and all plugins.
    Use this only when you installed `edwh` via pipx

    :param c: invoke ctx
    :type c: Context
    """
    try:
        _self_update(c, PIP_COMMAND_FOR_PIPX)
    except ModuleNotFoundError:
        print(colored("WARN: No `edwh` modules found. Perhaps you are NOT using pipx? Try ew self-update", "yellow"))
        exit(1)


@task()
def self_update(c):
    """
    Updates `edwh` and all plugins.
    Only use this command when using a virtualenv (not pipx!)

    :param c: invoke ctx
    :type c: Context
    """
    try:
        _self_update(c, "pip")
    except ModuleNotFoundError:
        print(colored("WARN: No `edwh` modules found. Perhaps you are using pipx? Try ew self-update-pipx", "yellow"))
        exit(1)
