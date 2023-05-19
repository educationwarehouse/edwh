"""
Extra namespace for plugin tasks such as plugin.add
"""
import concurrent.futures
import datetime
import sys
import typing

import requests
from invoke import task, Context
from packaging.version import parse as parse_package_version, InvalidVersion, Version
from termcolor import colored
from ..meta import (
    _pip,
    _get_available_plugins_from_pypi,
    _parse_versions,
    _gather_package_metadata_threaded,
    _get_latest_version_from_pypi,
)


def _plugins(c: Context, pip_command=_pip()) -> list[str]:
    """
    List installed edwh-plugins
    """
    return c.run(f'{pip_command} freeze | grep edwh', hide=True, warn=True).stdout.strip().split("\n")


@task(name="list")
def list_plugins(c, verbose=False):
    """
    List installed plugins

    :param c: invoke ctx
    :type c: Context

    :param verbose: should all info such as installed version always be shown?
    """
    available_plugins = ["edwh"] + _get_available_plugins_from_pypi('edwh', 'plugins')

    installed_plugins_raw = _plugins(c)

    if not installed_plugins_raw or len(installed_plugins_raw) == 1 and installed_plugins_raw[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")

    installed_plugins = _parse_versions(installed_plugins_raw)

    plugin_info = _gather_package_metadata_threaded(available_plugins)

    old_plugins = []
    not_all_installed = False
    for plugin in available_plugins:
        metadata = plugin_info[plugin]
        current_version = installed_plugins.get(plugin, None)
        latest_version = parse_package_version(metadata["info"]["version"]) if metadata else None
        if latest_version and current_version:
            is_outdated = latest_version > current_version
        else:
            is_outdated = False

        github_url = metadata["info"]["project_urls"]["Documentation"]
        requires_python = metadata["info"]["requires_python"]

        clean_name = plugin.removeprefix("edwh-").removesuffix("-plugin")
        if is_outdated:
            old_plugins.append(plugin)

            if verbose:
                plugin_details = (
                    f"• {clean_name} ({current_version} < {latest_version}) - {github_url} - Python {requires_python}"
                )
            else:
                plugin_details = f"• {clean_name} ({current_version} < {latest_version}) - {github_url}"

            print(
                colored(
                    plugin_details,
                    'yellow',
                )
            )
        elif plugin in installed_plugins:
            if verbose:
                plugin_details = f"• {clean_name} ({latest_version}) - {github_url} - Python {requires_python}"
            else:
                plugin_details = f"• {clean_name} - {github_url}"

            print(
                colored(
                    plugin_details,
                    'green',
                )
            )
        else:
            if verbose:
                plugin_details = f"◦ {clean_name} ({latest_version}) - {github_url} - Python {requires_python}"
            else:
                plugin_details = f"◦ {clean_name} - {github_url}"

            print(
                colored(
                    plugin_details,
                    'red',
                )
            )
            not_all_installed = clean_name

    if old_plugins:
        print()
        s = "" if len(old_plugins) == 1 else "s"
        verb = "is" if len(old_plugins) == 1 else "are"
        print(
            colored(f"{len(old_plugins)} plugin{s} {verb} out of date. Try `edwh self-update` to fix this.", "yellow")
        )

    if not_all_installed:
        print()
        print(
            colored(
                f"Tip: not all plugins are installed. For example, try `edwh plugin.add {not_all_installed}` or `edwh plugin.add all`",
                "blue",
            )
        )


def _require_affixes(package: str, prefix="edwh-", suffix="-plugin"):
    """
    affix is 'an addition to the base form or stem of a word in order to modify its meaning or create a new word.'
    """
    package = package.removeprefix(prefix).removesuffix(suffix)
    return f"{prefix}{package}{suffix}"


@task()
def add_all(c):
    """
    Install all available plugins

    Args:
        c (Context): invoke ctx
    """
    pip = _pip()
    plugins = _get_available_plugins_from_pypi('edwh', 'plugins')

    plugins = " ".join(plugins)
    c.run(f"{pip} install {plugins}")


@task()
def remove_all(c):
    """
    Remove all available plugins

    Args:
        c (Context): invoke ctx
    """
    pip = _pip()
    plugins = _get_available_plugins_from_pypi('edwh', 'plugins')

    plugins = " ".join(plugins)
    c.run(f"{pip} uninstall --yes {plugins}")


@task(aliases=('install',))
def add(c, plugin_name: str):
    """
    Install a new plugin

    Args:
        c (Context): invoke ctx
        plugin_name: which plugin to add
    """
    if plugin_name == "all":
        return add_all(c)

    pip = _pip()
    plugin_name = _require_affixes(plugin_name)

    c.run(f"{pip} install {plugin_name}")


@task(aliases=("upgrade",))
def update(c, plugin_name: str, version: str = None):
    """
    Update a plugin (or 'all') to the latest version

    Args:
        c (Context): invoke ctx
        plugin_name: the edwh plugin name (can be supplied without edwh- prefix or -plugin suffix)
        version: optional custom version string (e.g. 0.14.0b1 for a beta pre-release)
    """
    if plugin_name == "all":
        from ..tasks import self_update

        return self_update(c)

    pip = _pip()
    plugin_name = _require_affixes(plugin_name)
    # if version is supplied, choose that. Otherwise use the latest
    version = version or _get_latest_version_from_pypi(plugin_name)

    c.run(f"{pip} install {plugin_name}=={version}")


@task(aliases=('uninstall',))
def remove(c, plugin_name: str):
    """
    Remove a plugin (or 'all')

    Args:
        c (Context): invoke ctx
        plugin_name: which plugin to remove
    """
    if plugin_name == "all":
        return remove_all(c)
    pip = _pip()
    # ensure the prefix and suffix exist, but not twice:
    plugin_name = _require_affixes(plugin_name)

    c.run(f"{pip} uninstall {plugin_name}")
