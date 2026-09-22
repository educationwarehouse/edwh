import json
import os
import re
import sys
import typing as t
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

import humanize
from ewok import Context
from termcolor import colored, cprint

from .helpers import (
    AnyDict,
    active_compose_config_file_sets,
    dc_config,
    dump_set_as_list,
    noop,
)


def indent(text: str, prefix: str = "  ") -> str:
    return prefix + text


def dedent(text: str, prefix: str = "  ") -> str:
    return text.replace(prefix, "", 1)


def terminal_link(url: str, text: str | None = None) -> str:
    """
    Creëer een klikbare hyperlink voor de terminal met OSC 8 escape codes.

    Args:
        url (str): De URL waarnaar de link moet verwijzen
        text (str, optional): De tekst die getoond moet worden.
                             Als None, wordt de URL zelf getoond.

    Returns:
        str: Een string met embedded ANSI escape codes voor een klikbare link

    Voorbeeld:
        print(terminal_link('https://github.com', 'Naar GitHub'))
        print(terminal_link('https://example.com'))
    """
    if text is None:
        text = url

    # OSC 8 formaat: \033]8;;{url}\033\\{text}\033]8;;\033\\
    escape_mask = "\033]8;;{}\033\\{}\033]8;;\033\\"

    return escape_mask.format(url, text)


HOST_RE = re.compile(r"`(.*?)`")


def strip_host(s: str) -> str:
    matches: list[str] = HOST_RE.findall(s.strip())
    return matches[0]


class ServiceDict(TypedDict, total=False):
    name: str
    exposes: list[int]
    ports: list[str]
    domains: set[str]


class ProjectDict(TypedDict, total=False):
    name: str
    hostingdomain: str
    disk_usage_human: str
    disk_usage_raw: int
    settings: AnyDict
    services: list[ServiceDict]


class DataDict(TypedDict):
    server: str
    projects: list[ProjectDict]


def get_hosts_for_service(docker_service: AnyDict) -> set[str]:
    domains = set()

    for label, value in docker_service.get("labels", {}).items():
        if "Host" not in value:
            # irrelevant
            continue

        if "||" in value:
            # OR
            for host in value.split("||"):
                domains.add(strip_host(host))
        else:
            # only one
            domains.add(strip_host(value))

    return domains


class Discover:
    i: str
    data: DataDict

    def __init__(
        self,
        ctx: Context,
        du: bool = False,
        exposes: bool = False,
        ports: bool = False,
        host_labels: bool = True,
        short: bool = False,
        settings: bool = False,
        as_json: bool = False,
    ):
        self.ctx = ctx
        self.du = du
        self.exposes = exposes
        self.ports = ports
        self.host_labels = host_labels
        self.short = short
        self.settings = settings
        self.as_json = as_json

        print_fn = noop if as_json else cprint

        self.print_fn = t.cast(t.Callable[..., None], print_fn)
        self.reset()

    def reset(self) -> None:
        hostname = self.find_hostname()

        self.i = ""
        self.data = {
            "server": hostname,
            "projects": [],
        }

    @contextmanager
    def indent(self, prefix: str = "  ") -> t.Generator[None, None, None]:
        # context manager
        self.i = indent(self.i, prefix)
        yield
        self.i = dedent(self.i, prefix)

    def print(self, *args: t.Any, **kwargs: t.Any) -> None:
        sep = kwargs.pop("sep", " ")
        msg = sep.join([self.i, *args])
        self.print_fn(msg, **kwargs)

    def get_hostingdomain_from_env(self) -> str:
        if ran := self.ctx.run("cat .env | grep HOSTINGDOMAIN", echo=False, hide=True, warn=True):
            hosting_domain = ran.stdout.strip()
        else:
            hosting_domain = None

        return hosting_domain.strip().split("=")[-1] if hosting_domain else ""

    def find_compose_files(self) -> list[Path]:
        return [path for compose_files in self.find_compose_projects() for path in compose_files]

    def find_local_compose_files(self) -> list[Path]:
        paths = []
        try:
            ran = self.ctx.run(
                "find ./docker-compose.yaml ./docker-compose.yml */docker-compose.yaml */docker-compose.yml",
                echo=False,
                hide=True,
                warn=True,
            )
            paths = [Path(path) for path in ran.stdout.splitlines() if path]
        except Exception:
            pass

        return paths

    def find_compose_projects(self) -> list[list[Path]]:
        # Active projects come first so their complete, ordered override list wins over
        # the single default file found by the local scan.
        active_file_sets = active_compose_config_file_sets(self.ctx)
        compose_file_sets = active_file_sets + [[path] for path in self.find_local_compose_files()]

        ran = self.ctx.run("pwd -P", echo=False, hide=True)
        if not ran or not (working_directory := ran.stdout.strip()):
            raise EnvironmentError("Failed to determine the Compose discovery directory")

        seen: set[Path] = set()
        projects: list[list[Path]] = []
        for compose_files in compose_file_sets:
            project_directory = compose_files[0].parent
            # These paths belong to the target host. Path.resolve() would resolve
            # relative paths on the machine running edwh, which is wrong over Fabric.
            project_key = Path(os.path.normpath(Path(working_directory) / project_directory))
            if project_key not in seen:
                seen.add(project_key)
                projects.append(compose_files)

        return projects

    def find_hostname(self) -> str:
        if ran := self.ctx.run("hostname", hide=True):
            return ran.stdout.strip()
        else:
            return ""

    def get_disk_usage(self) -> tuple[str, int]:
        if ran := self.ctx.run("du -sh . --block-size=1", echo=False, hide=True):
            usage_raw = ran.stdout.strip().split("\t")[0]
            usage = humanize.naturalsize(usage_raw, binary=True)
            self.print(f"Disk usage: {usage}", color="red", attrs=["bold"])

            return usage, int(usage_raw)
        else:
            raise EnvironmentError("Failed running `du`")

    def get_settings(self, folder: str) -> AnyDict | None:
        json_flag = "--json" if self.as_json else ""
        if ran := self.ctx.run(f"~/.local/bin/edwh settings {json_flag}", echo=False, hide=True):
            settings_output = ran.stdout.strip()
        else:
            settings_output = ""

        if self.as_json:
            try:
                return t.cast(AnyDict, json.loads(settings_output))
            except json.JSONDecodeError:
                print(f"Error loading settings for {self.data['server']}/{folder}", file=sys.stderr)
        else:
            self.print("Settings:", color="red", attrs=["bold"])
            with self.indent():
                for line in settings_output.split("\n"):
                    self.print(line)
        return None

    def process_docker_service(self, name: str, docker_service: AnyDict, hosting_domain: str) -> ServiceDict:
        service: ServiceDict = {"name": name}
        if not self.short:
            self.print(name, color="green")
        with self.indent():
            if self.exposes and not self.short:
                if _exposes := docker_service.get("expose", []):
                    self.print(f"Exposes: {', '.join([str(port) for port in _exposes])}", color="red", attrs=["bold"])
                service["exposes"] = _exposes
            if self.ports:
                if _ports := docker_service.get("ports", []):
                    self.print(
                        f"Ports: {', '.join([str(port) for port in _ports]) if _ports else ''}",
                        color="red",
                        attrs=["bold"],
                    )
                service["ports"] = _ports

            service["domains"] = set()
            if self.host_labels and not self.short:
                service["domains"] = get_hosts_for_service(docker_service)
                for domain in service["domains"]:
                    self.print(
                        terminal_link(
                            f"https://{domain}",
                            domain.replace(hosting_domain, colored(hosting_domain, color="dark_grey")),
                        ),
                    )

        if service["domains"]:
            self.print()

        return service

    def process_omgeving(self, folder: str, compose_files: list[Path] | None = None) -> ProjectDict | None:
        project: ProjectDict = {}
        hosting_domain = self.get_hostingdomain_from_env()
        self.print(
            colored(f"{folder}", color="light_blue"),
            colored(f"{hosting_domain}", color="light_yellow"),
        )

        project["name"] = folder
        project["hostingdomain"] = hosting_domain

        with self.indent():
            config = dc_config(self.ctx, compose_files=compose_files)
            if config is None:
                return None

            if self.du and not self.short:
                usage, usage_raw = self.get_disk_usage()
                project["disk_usage_human"] = usage
                project["disk_usage_raw"] = usage_raw

            if self.settings and (settings := self.get_settings(folder)) and not self.short:
                project["settings"] = settings

            project["services"] = []
            # if not self.short:
            #     print(config.get("services", {}).items())
            for name, docker_service in config.get("services", {}).items():
                project["services"].append(self.process_docker_service(name, docker_service, hosting_domain))

        return project

    def process_compose_file(self, compose_file_path: Path) -> None:
        folder = compose_file_path.parent
        with self.ctx.cd(folder):
            if project := self.process_omgeving(str(folder)):
                self.data["projects"].append(project)

    def process_compose_project(self, compose_files: list[Path]) -> None:
        folder = compose_files[0].parent
        compose_files = [
            path if path.is_absolute() else Path(os.path.relpath(path, start=folder)) for path in compose_files
        ]
        with self.ctx.cd(folder):
            if project := self.process_omgeving(str(folder), compose_files=compose_files):
                self.data["projects"].append(project)

    def discover(self) -> None:
        self.reset()

        self.print(self.data["server"], attrs=["bold"])

        compose_file_sets = self.find_compose_projects()

        for compose_files in compose_file_sets:
            self.process_compose_project(compose_files)

        if self.as_json:
            print(json.dumps({"data": self.data}, indent=2, default=dump_set_as_list))


def discover(
    ctx: Context,
    du: bool = False,
    exposes: bool = False,
    ports: bool = False,
    host_labels: bool = True,
    short: bool = False,
    settings: bool = False,
    as_json: bool = False,
) -> None:
    d = Discover(
        ctx,
        du=du,
        exposes=exposes,
        ports=ports,
        host_labels=host_labels,
        short=short,
        settings=settings,
        as_json=as_json,
    )

    return d.discover()
