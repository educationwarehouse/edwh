"""
Extra namespace for plugin tasks such as plugin.add
"""
import json
import typing
from dataclasses import dataclass

from invoke import task, Context
from packaging.version import parse as parse_package_version
from termcolor import colored

from ..meta import (
    _pip,
    _get_available_plugins_from_pypi,
    _parse_versions,
    _gather_package_metadata_threaded,
    _get_latest_version_from_pypi,
    Version,
)


def _plugins(c: Context, pip_command=_pip()) -> list[str]:
    """
    List installed edwh-plugins
    """
    return c.run(f'{pip_command} freeze | grep edwh', hide=True, warn=True).stdout.strip().split("\n")


@dataclass
class Plugin:
    raw_name: str
    installed_version: typing.Optional[Version]
    latest_version: typing.Optional[Version]
    metadata: dict

    is_installed: bool
    clean_name: str = ""
    is_outdated: bool = False

    def __post_init__(self):
        if self.latest_version and self.installed_version:
            self.is_outdated = self.latest_version > self.installed_version

        self.clean_name = self.raw_name.removeprefix("edwh-").removesuffix("-plugin")
        self.github_url = self.metadata["info"]["project_urls"]["Documentation"]
        self.requires_python = self.metadata["info"]["requires_python"]

    def __repr__(self):
        return f"<EW Plugin: {self.clean_name}-{(self.installed_version if self.is_installed else self.latest_version) or '?'} {'installed' if self.is_installed else 'available'}>"

    def __str__(self):
        return json.dumps(self.__dict__)

    def print_details(self, verbose=False):
        if self.is_outdated:
            if verbose:
                plugin_details = f"• {self.clean_name} ({self.installed_version} < {self.latest_version}) - {self.github_url} - Python {self.requires_python}"
            else:
                plugin_details = (
                    f"• {self.clean_name} ({self.installed_version} < {self.latest_version}) - {self.github_url}"
                )

            print(
                colored(
                    plugin_details,
                    'yellow',
                )
            )
        elif self.is_installed:
            if verbose:
                plugin_details = (
                    f"• {self.clean_name} ({self.latest_version}) - {self.github_url} - Python {self.requires_python}"
                )
            else:
                plugin_details = f"• {self.clean_name} - {self.github_url}"

            print(
                colored(
                    plugin_details,
                    'green',
                )
            )
        else:
            if verbose:
                plugin_details = (
                    f"◦ {self.clean_name} ({self.latest_version}) - {self.github_url} - Python {self.requires_python}"
                )
            else:
                plugin_details = f"◦ {self.clean_name} - {self.github_url}"

            print(
                colored(
                    plugin_details,
                    'red',
                )
            )


def get_installed_plugin_info(c: Context) -> list[Plugin]:
    """
    For all available plugins, get a Plugin instance with info
    """
    available_plugins = ["edwh"] + _get_available_plugins_from_pypi('edwh', 'plugins')
    installed_plugins_raw = _plugins(c)
    if not installed_plugins_raw or len(installed_plugins_raw) == 1 and installed_plugins_raw[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")
    installed_plugins = _parse_versions(installed_plugins_raw)
    plugin_info = _gather_package_metadata_threaded(available_plugins)

    return [
        Plugin(
            raw_name=plugin,
            is_installed=plugin in installed_plugins,
            installed_version=installed_plugins.get(plugin),
            latest_version=parse_package_version(plugin_info[plugin]["info"]["version"])
            if plugin_info.get(plugin)
            else None,
            metadata=plugin_info.get(plugin),
        )
        for plugin in available_plugins
    ]

    # return available_plugins, installed_plugins, plugin_info


@task(name="list")
def list_plugins(c, verbose=False):
    """
    List installed plugins

    :param c: invoke ctx
    :type c: Context

    :param verbose: should all info such as installed version always be shown?
    """
    plugins = get_installed_plugin_info(c)

    old_plugins = []
    not_all_installed = False
    for plugin in plugins:
        plugin.print_details(verbose=verbose)
        if plugin.is_outdated:
            old_plugins.append(plugin)
        if not plugin.is_installed:
            not_all_installed = plugin.clean_name

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
    if package == "edwh":
        # don't require affixes!
        return package

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

    c.run(f"{pip} uninstall --yes {plugin_name}")
