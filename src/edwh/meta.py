"""
This files contains everything to do with meta-tasks such as self-updating
"""

import concurrent.futures
import sys
import typing
from typing import Optional

import yayarl as yarl
from ewok import task
from invoke.context import Context
from packaging.version import InvalidVersion, Version
from packaging.version import parse as parse_package_version
from termcolor import cprint

from .helpers import AnyDict

PYPI_URL_BASE = yarl.URL("https://pypi.python.org/pypi/")


def _python() -> str:
    """
    used to detect current Python environment, even in pipx
    """
    return sys.executable


def _pip(python: str = _python()) -> str:
    """
    used to detect current pip environment, even in pipx
    """
    # uv.find_uv_bin() does not really work here, because then the right venv may not be used!
    return f"{python} -m uv pip"


def _get_pypi_info(package: str) -> AnyDict:
    """
    Load metadata from pypi for a package
    """
    url = PYPI_URL_BASE / package / "json"
    resp = url.get(timeout=10)
    return typing.cast(AnyDict, resp.json())


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
        extras = [_.split(";")[0] for _ in extras if _.endswith(f'; extra == "{extra}"')]

    return list(extras)


def _gather_package_metadata_threaded(packages: typing.Iterable[str]) -> dict[str, AnyDict | None]:
    """
    For any package in packages, gather its metadata from pypi
    """
    all_data: dict[str, AnyDict | None] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        pkg_names = [_.split("==")[0] for _ in packages]
        for result, package in zip(executor.map(_get_pypi_info, pkg_names), packages):
            all_data[package] = result

    return all_data


def _determine_newest_version(releases: typing.Collection[str]) -> str:
    sorted_releases = sorted(releases, key=Version)
    return sorted_releases[-1]


def _determine_outdated_threaded(
    installed_plugins: typing.Collection[str], prerelease: bool = False
) -> dict[str, Version]:
    """
    Like _determine_outdated but parallelized with Threading

    installed_plugins is a list (or other iterable) of ["name==version", "name @ location"] type strings
    """
    plugins_metadata = _gather_package_metadata_threaded([_ for _ in installed_plugins if " @ " not in _])

    outdated = {}
    for plugin, metadata in plugins_metadata.items():
        if not metadata:
            continue

        try:
            name, current_version_str = plugin.split("==")
            current_version = parse_package_version(current_version_str)

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
def plugins(c: Context, verbose: bool = False, changelog: bool = False) -> None:
    """
    alias for plugin.list or plugin.changelog --new
    """
    from .local_tasks import plugin

    if changelog:
        return plugin.changelog(c, [], new=True)
    else:
        return plugin.list_plugins(c, verbose=verbose)


def _self_update(c: Context, prerelease: bool = False, no_cache: bool = False) -> None:
    """
    Wrapper for self-update that can handle type hint Context
    """
    from .local_tasks.plugin import list_installed_plugins

    pip_command = _pip()

    edwh_packages = list_installed_plugins(c, pip_command)
    if not edwh_packages or (len(edwh_packages) == 1 and edwh_packages[0] == ""):
        cprint("No 'edwh' packages found. That can't be right", color="yellow")

    old_plugins = _determine_outdated_threaded(edwh_packages, prerelease=prerelease)

    if not old_plugins:
        cprint("Nothing to update", "blue")
        exit()

    cprint(f"Will try to update {len(old_plugins)} packages.", "blue")

    success = []
    failure = []
    for plugin, version in old_plugins.items():
        command = f"{pip_command} install {plugin}=={version}"
        if no_cache:
            command = f"{command} --no-cache"

        result = c.run(command, warn=True)

        if result and result.return_code == 0:
            success.append(plugin)
        else:
            failure.append(plugin)

    if success:
        cprint(f"{len(success)}/{len(old_plugins)} updated successfully.", "green")

    if failure:
        cprint(f"{', '.join(failure)} failed updating", "red")


@task(
    flags={
        "prerelease": ["prerelease", "pre", "pre-release", "p"],
        "no_cache": ["no-cache", "f", "fresh"],
    }
)
def self_update(c: Context, prerelease: bool = False, no_cache: bool = False) -> None:
    """Updates `edwh` and all installed plugins.

    Args:
        c (Context): invoke ctx
        prerelease (bool, optional): allow non-stable releases? Defaults to False.
        no_cache (bool, optional): download fresh? Defaults to False.
    """
    return _self_update(c, prerelease, no_cache)


def is_installed(ctx: Context, command: str) -> bool:
    """
    Check if a bash command is known.
    """
    return ctx.run(f"which {command}", hide="both", warn=True).ok
