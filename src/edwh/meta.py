"""
This files contains everything to do with meta-tasks such as self-updating
"""

import concurrent.futures
import sys
import typing
from typing import Optional

import requests
from invoke import Context, task
from packaging.version import InvalidVersion, Version
from packaging.version import parse as parse_package_version
from termcolor import cprint

PYPI_URL_PATTERN = "https://pypi.python.org/pypi/{package}/json"


def _python() -> str:
    """
    used to detect current Python environment, even in pipx
    """
    return sys.executable


def _pip(python=_python()) -> str:
    """
    used to detect current pip environment, even in pipx
    """
    return f"{python} -m pip"


def _get_pypi_info(package: str) -> dict:
    """
    Load metadata from pypi for a package
    """
    return requests.get(PYPI_URL_PATTERN.format(package=package), timeout=10).json()


def _get_latest_version_from_pypi(package: str) -> Version:
    """
    Get the latest Version for a package  from pypi
    """
    data = _get_pypi_info(package)
    if not data or not data.get("info"):
        raise ModuleNotFoundError(f"Plugin {package} does not seem to exist.")

    return parse_package_version(data["info"]["version"])


def _get_available_plugins_from_pypi(package: str, extra: Optional[str] = None) -> list[str]:
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


def _determine_newest_version(releases: typing.Iterable[str]) -> str:
    sorted_releases = sorted(releases, key=lambda _: Version(_))
    return sorted_releases[-1]


def test_me():
    metadata = _gather_package_metadata_threaded(["edwh"])["edwh"]
    print(parse_package_version(_determine_newest_version(metadata["releases"].keys())))


def _determine_outdated_threaded(
    installed_plugins: typing.Iterable[str], prerelease: bool = False
) -> dict[str, Version]:
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

            latest_stable = metadata["info"]["version"]
            latest_prerelease = _determine_newest_version(metadata["releases"].keys()) if prerelease else None
            latest_version = parse_package_version(latest_prerelease if prerelease else latest_stable)
        except Exception:
            # no current or latest version found? skip
            continue

        if current_version and latest_version and latest_version > current_version:
            outdated[name] = latest_version

    return outdated


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
def plugins(c, verbose=False, changelog=False):
    """
    alias for plugin.list or plugin.changelog --new
    """
    from .local_tasks import plugin

    if changelog:
        return plugin.changelog(c, [], new=True)
    else:
        return plugin.list_plugins(c, verbose=verbose)


def _self_update(c: Context, prerelease: bool = False):
    """
    Wrapper for self-update that can handle type hint Context
    """
    from .local_tasks.plugin import list_installed_plugins

    pip_command = _pip()

    edwh_packages = list_installed_plugins(c, pip_command)
    if not edwh_packages or len(edwh_packages) == 1 and edwh_packages[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")

    old_plugins = _determine_outdated_threaded(edwh_packages, prerelease=prerelease)

    if not old_plugins:
        cprint("Nothing to update", "blue")
        exit()

    cprint(f"Will try to update {len(old_plugins)} packages.", "blue")

    success = []
    failure = []
    for plugin, version in old_plugins.items():
        result = c.run(f"{pip_command} install {plugin}=={version}", warn=True).stdout

        if f"Successfully installed {plugin}" in result:
            success.append(plugin)
        else:
            failure.append(plugin)

    if success:
        cprint(f"{len(success)}/{len(old_plugins)} updated successfully.", "green")
    if failure:
        cprint(f"{', '.join(failure)} failed updating", "red")


@task()
def self_update(c, prerelease: bool = False):
    """
    Updates `edwh` and all installed plugins.

    :param c: invoke ctx
    :type c: Context
    :param prerelease: allow non-stable releases?
    """
    return _self_update(c, prerelease)
