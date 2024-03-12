"""
Extra namespace for plugin tasks such as plugin.add
"""
import concurrent.futures
import datetime as dt
import json
import re
import typing
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import dateutil.parser
import requests
import yarl
from invoke import Context, task
from packaging.version import parse as parse_package_version
from termcolor import colored, cprint

from .. import confirm, kwargs_to_options
from ..meta import (
    Version,
    _gather_package_metadata_threaded,
    _get_available_plugins_from_pypi,
    _get_latest_version_from_pypi,
    _parse_versions,
    _pip,
)


def list_installed_plugins(c: Context, pip_command: Optional[str] = None) -> list[str]:
    """
    List installed edwh-plugins
    """
    if not pip_command:
        pip_command = _pip()

    packages = c.run(f"{pip_command} freeze | grep edwh", hide=True, warn=True).stdout.strip().split("\n")

    # filter out comments and editable (local) installs:
    return [_ for _ in packages if not (_.startswith("#") or _.startswith("-e"))]


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
        version = (self.installed_version if self.is_installed else self.latest_version) or "?"
        return f"<EW Plugin: {self.clean_name}-{version} {'installed' if self.is_installed else 'available'}>"

    def __str__(self):
        return json.dumps(self.__dict__)

    def print_details(self, verbose=False):
        if self.is_outdated:
            if verbose:
                plugin_details = (
                    f"• {self.clean_name} "
                    f"({self.installed_version} < {self.latest_version}) "
                    f"- {self.github_url} "
                    f"- Python {self.requires_python}"
                )
            else:
                plugin_details = (
                    f"• {self.clean_name} ({self.installed_version} < {self.latest_version}) - {self.github_url}"
                )

            cprint(
                plugin_details,
                "yellow",
            )
        elif self.is_installed:
            if verbose:
                plugin_details = (
                    f"• {self.clean_name} ({self.latest_version}) - {self.github_url} - Python {self.requires_python}"
                )
            else:
                plugin_details = f"• {self.clean_name} - {self.github_url}"

            cprint(
                plugin_details,
                "green",
            )
        else:
            if verbose:
                plugin_details = (
                    f"◦ {self.clean_name} ({self.latest_version}) - {self.github_url} - Python {self.requires_python}"
                )
            else:
                plugin_details = f"◦ {self.clean_name} - {self.github_url}"

            cprint(
                plugin_details,
                "red",
            )


def _gather_plugin_info(c: Context, plugin_names: list[str]) -> list[Plugin]:
    """
    For all queried plugins (in `plugin_names`), get a Plugin instance with info.
    """
    installed_plugins_raw = list_installed_plugins(c)
    installed_plugins = _parse_versions(installed_plugins_raw)
    plugin_names = [_require_affixes(_) for _ in plugin_names]
    plugin_infos = _gather_package_metadata_threaded(plugin_names)

    result = []

    for plugin_name in plugin_names:
        metadata = plugin_infos.get(plugin_name, {})
        if not (metadata and (info := metadata.get("info"))):
            # invalid plugin
            continue

        result.append(
            Plugin(
                raw_name=plugin_name,
                is_installed=plugin_name in installed_plugins,
                installed_version=installed_plugins.get(plugin_name),
                latest_version=parse_package_version(info["version"]),
                metadata=metadata,
            )
        )

    return result


def gather_plugin_info(c: Context) -> list[Plugin]:
    """
    For all available plugins, get a Plugin instance with info
    """
    available_plugins = ["edwh", *_get_available_plugins_from_pypi("edwh", "plugins")]
    installed_plugins_raw = list_installed_plugins(c)
    if not installed_plugins_raw or len(installed_plugins_raw) == 1 and installed_plugins_raw[0] == "":
        raise ModuleNotFoundError("No 'edwh' packages found. That can't be right")

    return _gather_plugin_info(c, available_plugins)


@task(name="list")
def list_plugins(c, verbose=False):
    """
    List installed plugins

    :param c: invoke ctx
    :type c: Context

    :param verbose: should all info such as installed version always be shown?
    """
    plugins = gather_plugin_info(c)

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
        cprint(
            f"{len(old_plugins)} plugin{s} {verb} out of date. "
            f"Try `edwh self-update` to fix this "
            f"or `edwh plugins --changelog` to see what's new.",
            "yellow",
        )

    if not_all_installed:
        print()
        cprint(
            f"Tip: not all plugins are installed. "
            f"For example, try `edwh plugin.add {not_all_installed}` or `edwh plugin.add all`",
            "blue",
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
    plugins = _get_available_plugins_from_pypi("edwh", "plugins")

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
    plugins = _get_available_plugins_from_pypi("edwh", "plugins")

    plugins = " ".join(plugins)
    c.run(f"{pip} uninstall --yes {plugins}")


@task(aliases=("install",))
def add(c, plugin_names: str):
    """
    Install a new plugin

    Args:
        c (Context): invoke ctx
        plugin_name: which plugin to add
    """
    if plugin_names == "all":
        return add_all(c)

    pip = _pip()

    plugin_names = [_require_affixes(plugin_name.strip()) for plugin_name in plugin_names.split(",")]

    c.run(f"{pip} install " + " ".join(plugin_names))


@task(aliases=("upgrade",))
def update(c, plugin_names: str, version: Optional[str] = None, verbose: bool = False):
    """
    Update a plugin (or 'all') to the latest version

    Args:
        c (Context): invoke ctx
        plugin_names: the edwh plugin name (can be supplied without edwh- prefix or -plugin suffix)
        version: optional custom version string (e.g. 0.14.0b1 for a beta pre-release)
        verbose: show which will would be installed for each plugin
    """
    if plugin_names == "all":
        from ..tasks import self_update

        return self_update(c)

    pip = _pip()

    plugins_with_version = []
    for plugin_name in plugin_names.split(","):
        plugin_name = _require_affixes(plugin_name.strip())
        plugin_version = version or _get_latest_version_from_pypi(plugin_name)
        plugins_with_version.append(f"{plugin_name}=={plugin_version}")

    if verbose:
        cprint(str(plugins_with_version), "blue")

    c.run(f"{pip} install " + " ".join(plugins_with_version))


@task(aliases=("uninstall",))
def remove(c, plugin_names: str):
    """
    Remove a plugin (or 'all')

    Args:
        c (Context): invoke ctx
        plugin_names: which plugin to remove
    """
    if plugin_names == "all":
        return remove_all(c)
    pip = _pip()
    # ensure the prefix and suffix exist, but not twice:
    plugin_names = [_require_affixes(plugin_name.strip()) for plugin_name in plugin_names.split(",")]

    c.run(f"{pip} uninstall --yes " + " ".join(plugin_names))


GITHUB_RAW_URL = yarl.URL("https://raw.githubusercontent.com")


def get_changelog(github_repo: str | yarl.URL):
    if isinstance(github_repo, str):
        github_repo = yarl.URL(github_repo)

    github_repo = github_repo.path.removeprefix("/")  # e.g. educationwarehouse/edwh
    changelog_url = GITHUB_RAW_URL / github_repo / "master/CHANGELOG.md"  # replace github.com with github raw

    return requests.get(str(changelog_url), timeout=10).text


def get_changelogs_threaded(github_repos: dict[str, str]):
    """
    For any package in packages, gather its metadata from pypi
    """
    all_data: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        repo_urls = list(github_repos.values())
        for result, package in zip(executor.map(get_changelog, repo_urls), github_repos.keys()):
            all_data[package] = result

    return all_data


def _filter_away_version(changelog_version: Version, _filter: str) -> bool:
    """
    If _filter is a Version and it's bigger than the selected row (via 'changelog_version'),
    the row should not be visible.
    """
    try:
        filter_version = parse_package_version(_filter)
        return changelog_version <= filter_version
    except Exception:
        return False


def _filter_away_date(date: dt.datetime, _filter: str) -> bool:
    """
    If _filter is a date and it's bigger than the selected row (via 'date'), the row should not be visible.
    """
    try:
        return date <= dateutil.parser.parse(_filter)
    except Exception:
        return False


def _filter_away(version: Version, date: dt.datetime, _filter: str) -> bool:
    """
    If a filter is numeric, it's probably not a version or date (it could be parsed as one but we want other behavior).
    If it is not numeric, try filtering away low version or dates.

    Returns True if a row can be removed and False if it has to stay.
    """
    return (not _filter.isnumeric()) and (_filter_away_version(version, _filter) or _filter_away_date(date, _filter))


def sort_versions(key_value: tuple[str, typing.Any]) -> Version:
    """
    Can be used as key=sort_versions in sort_and_filter_changelog
    """
    key, value = key_value

    try:
        version, date = key.split(" ")
        return parse_package_version(version)
    except Exception:
        # something went wrong, return something so sorting doesn't crash:
        return Version("0.0.0")


def parse_changelog(markdown: str):
    """
    Parse our CHANGELOG.md to a dictionary of {version: {type: [list of changes]}}
    where version is e.g. v0.18.5 (2023-06-06)
    where type is e.g. Fix
    """
    # thanks ChatGPT
    changelog = {}
    current_version = None
    current_category = None

    lines = markdown.split("\n")
    for line in lines:
        if line.startswith("# Changelog"):
            continue

        version_match = re.match(r"^## (.+)", line)
        if version_match:
            version = version_match.group(1)
            changelog[version] = {}
            current_version = version
            continue

        category_match = re.match(r"^### (.+)", line)
        if category_match:
            category = category_match.group(1)
            changelog[current_version][category] = []
            current_category = category
            continue

        feature_match = re.match(r"^\* (.+)", line)
        if feature_match:
            feature = feature_match.group(1)
            changelog[current_version][current_category].append(feature)

    return changelog


def to_date(key: str):
    """
    Convert a changelog key `v0.0.0 (2000-01-01)` to a dt.datetime
    """
    try:
        _, date = key.split(" ", 1)
        return dateutil.parser.parse(date.removeprefix("(").removesuffix(")"))
    except Exception:
        return dateutil.parser.parse("2000-01-01")


def to_version(key: str):
    """
    Convert a changelog key `v0.0.0 (2000-01-01)` to a Version(0.0.0)
    """
    try:
        key, _ = key.split(" ", 1)
        return parse_package_version(key)
    except Exception:
        return Version("0.0.0")


def sort_and_filter_changelog(changelog: dict, since: Optional[str] = None):
    """
    Since can be:
    - a number - amount of releases to show.
    - a version number - show changes starting from that version.
    - a date - show changes starting from that date.
    - major, minor, patch - show changes starting from the latest release of that type.
    """
    filtered = {}

    prev_major = prev_minor = prev_patch = 0

    for idx, (k, v) in enumerate(changelog.items()):
        version = to_version(k)
        date = to_date(k)

        # checks to stop:
        if (
            (since == "major" and version.major < prev_major)
            or (since == "minor" and (version.minor < prev_minor or version.major < prev_major))
            or (
                since == "patch"
                and (version.micro < prev_patch or version.minor < prev_minor or version.major < prev_major)
            )
            or (since.isnumeric() and idx >= int(since))
        ):
            break

        # checks to skip:
        elif _filter_away(version, date, since):
            # skip!
            continue

        prev_major = version.major
        prev_minor = version.minor
        prev_patch = version.micro
        # checks passed, add to output
        filtered[k] = v

    return OrderedDict(sorted(filtered.items(), reverse=True, key=sort_versions))


COLORS = {
    "fix": "yellow",
    "feature": "green",
    "documentation": "blue",
}

BOLD_RE = re.compile(r"((\*\*|__).+?(\*\*|__))")


def colored_markdown(text: str):
    """
    Prettify a changelog line (makes ** bold).

    todo: more than bold?
    """
    final = ""
    for part in BOLD_RE.split(text):
        if part.startswith("**") and part.endswith("**"):
            part = colored(part.removeprefix("**").removesuffix("**"), attrs=["bold"])
        final += part
    return final


def display_changelogs(changelogs: dict[str, OrderedDict]):
    """
    Final step of changelog(), uses the result of {package: sort_and_filter_changelog()}.
    """
    for package, history in changelogs.items():
        cprint(package, "red", attrs=["bold", "underline"])
        for version, changes in history.items():
            print("-", version)
            for change_type, change_descriptions in changes.items():
                print("--", colored(change_type, COLORS.get(change_type.lower(), "white")))
                for change in change_descriptions:
                    print("----", colored_markdown(change))


def _gather_and_display_changelogs(info: list[Plugin], since: dict[str, str]):
    changelogs = get_changelogs_threaded(
        {plugin.clean_name: plugin.metadata["info"]["project_urls"]["Source"] for plugin in info}
    )

    changelogs = {
        name: (
            # sort and filter removes everything not matching 'since' and sorts by date (/version) desc.
            sort_and_filter_changelog(
                # parse_changelog converts the markdown to a dict
                parse_changelog(data),
                # 'since' filter can differ per plugin if --new is passed.
                since[name],
            )
        )
        for name, data in changelogs.items()
    }

    display_changelogs(changelogs)


def _changelog_new(ctx: Context, *_):
    """
    List changes since last installed version.
    """
    info = [plugin for plugin in gather_plugin_info(ctx) if plugin.is_outdated]
    # if --new, ignore --since argument
    since = {plugin.clean_name: str(plugin.installed_version) for plugin in info}

    return _gather_and_display_changelogs(info, since)


def _changelog_specific(ctx: Context, plugin_names: list[str], since: str, *_):
    """
    List changes for specific plugins.
    """
    info = _gather_plugin_info(ctx, plugin_names)
    _since = {plugin.clean_name: since for plugin in info}

    return _gather_and_display_changelogs(info, _since)


def _changelog_all(ctx: Context, _: list[str], since: str, *__):
    """
    List changes for all plugins.
    """
    info = gather_plugin_info(ctx)
    _since = {plugin.clean_name: since for plugin in info}

    return _gather_and_display_changelogs(info, _since)


@task(iterable=["plugin"])
def changelog(ctx, plugin: list[str], since: str = "5", new: bool = False):
    """
    Show changelogs for edwh plugins.
    by default, changelogs from all plugins are shown.
    Since can be used to filter/limit changes. By default, the last 5 releases are shown.
    Since can be a number (amount of changes), a date (show releases from that date),
    a version (releases starting from that version) or
    'major'/'minor'/'patch' to show releases since the latest version of that type.
    if 'new' is True, show only changes for outdated packages.
    """
    if new:
        return _changelog_new(ctx, plugin, since, new)
    elif plugin:
        return _changelog_specific(ctx, plugin, since, new)
    else:
        return _changelog_all(ctx, plugin, since, new)


def _semantic_release_publish(c: Context, flags: dict[str, typing.Any], **kw) -> typing.Optional[str]:
    semver = c.run(f"semantic-release publish {kwargs_to_options(flags)}", **kw)

    if new_version := re.findall(r"to (\d+\.\d+\.\d+.*)", semver.stderr if semver else ""):
        return new_version[0]

    cprint("No new version found!", "yellow")
    return None


@task(aliases=("publish",))
def release(
    c,
    noop: bool = False,
    major: bool = False,
    minor: bool = False,
    patch: bool = False,
    prerelease: bool = False,
    yes: bool = False,
):
    """
    Release a new version of a plugin.

    Args:
        c (Context)
        noop: don't actually publish anything, just show what would happen
        major: bump major version
        minor: bump minor version
        patch: bump patch version
        prerelease: release as beta version (e.g. 1.0.0b1)
        yes: don't ask for confirmation
    """
    cprint("bumping version", "blue")

    if not (yes or noop):
        new_version = _semantic_release_publish(
            c,
            {
                "noop": True,
                "major": major,
                "minor": minor,
                "patch": patch,
                "prerelease": prerelease,
            },
            hide=True,
        )

        if not new_version or not confirm(
            f"Are you sure you would like to release version {new_version}? [yN] ", default=False
        ):
            print("bye!")
            return

    new_version = _semantic_release_publish(
        c,
        {
            "noop": noop,
            "major": major,
            "minor": minor,
            "patch": patch,
            "prerelease": prerelease,
        },
    )

    if not new_version:
        return

    cprint("Starting build", "blue")
    hatch_build = c.run("hatch build -c")

    pkg = re.findall(r"dist/(.+)-\d+\.\d+\.\d+.+tar\.gz", hatch_build.stderr)

    if not noop:
        cprint("Starting release", "blue")
        c.run("hatch publish")
        cprint(f"{pkg} {new_version} released!", "green")
    else:
        cprint(f"Not publishing {pkg} {new_version} due to --noop", "yellow")
