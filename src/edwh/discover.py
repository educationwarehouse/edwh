import json
import re
import sys
import typing
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

import humanize

# todo: replace 'ansi' with termcolor
from ansi.color import fg
from ansi.color.fx import bold, reset
from invoke.context import Context

from .helpers import AnyDict, dc_config, dump_set_as_list, noop


def indent(text: str, prefix: str = "  ") -> str:
    return prefix + text


def dedent(text: str, prefix: str = "  ") -> str:
    return text.replace(prefix, "", 1)


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

        print_fn = noop if as_json else print

        self.print_fn = typing.cast(typing.Callable[..., None], print_fn)
        self.reset()

    def reset(self) -> None:
        hostname = self.find_hostname()

        self.i = ""
        self.data = {
            "server": hostname,
            "projects": [],
        }

    @contextmanager
    def indent(self, prefix: str = "  ") -> typing.Generator[None, None, None]:
        # context manager
        self.i = indent(self.i, prefix)
        yield
        self.i = dedent(self.i, prefix)

    def print(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        self.print_fn(self.i, *args, **kwargs)

    def get_hostingdomain_from_env(self) -> str:
        if ran := self.ctx.run("cat .env | grep HOSTINGDOMAIN", echo=False, hide=True, warn=True):
            hosting_domain = ran.stdout.strip()
        else:
            hosting_domain = None

        return hosting_domain.strip().split("=")[-1] if hosting_domain else ""

    def find_compose_files(self) -> list[str]:
        try:
            ran = self.ctx.run(
                "find */docker-compose.yaml */docker-compose.yml",
                echo=False,
                hide=True,
                warn=True,
            )
            return ran.stdout.strip().split("\n")
        except Exception:
            return []

    def find_hostname(self) -> str:
        if ran := self.ctx.run("hostname", hide=True):
            return ran.stdout.strip()
        else:
            return ""

    def get_disk_usage(self) -> tuple[str, int]:
        if ran := self.ctx.run("du -sh . --block-size=1", echo=False, hide=True):
            usage_raw = ran.stdout.strip().split("\t")[0]
            usage = humanize.naturalsize(usage_raw, binary=True)
            self.print(f"{fg.boldred}Disk usage: {usage}{reset}")

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
                return typing.cast(AnyDict, json.loads(settings_output))
            except json.JSONDecodeError:
                print(f"Error loading settings for {self.data['server']}/{folder}", file=sys.stderr)
        else:
            self.print(f"{fg.boldred}Settings:", reset)
            with self.indent():
                for line in settings_output.split("\n"):
                    self.print(line)
        return None

    def process_docker_service(self, name: str, docker_service: AnyDict, hosting_domain: str) -> ServiceDict:
        service: ServiceDict = {"name": name}

        self.print(f"{fg.green}{name}{reset}")
        with self.indent():
            if self.exposes:
                if _exposes := docker_service.get("expose", []):
                    self.print(f"{fg.boldred}Exposes: {', '.join([str(port) for port in _exposes])}{reset}")
                service["exposes"] = _exposes
            if self.ports:
                if _ports := docker_service.get("ports", []):
                    self.print(
                        f"{fg.boldred}Ports: {', '.join([str(port) for port in _ports]) if _ports else ''}{reset}"
                    )
                service["ports"] = _ports

            service["domains"] = set()
            if self.host_labels:

                def darken_domain(s: str) -> str:
                    return s.replace(hosting_domain, f"{fg.brightblack}{hosting_domain}{reset}")

                service["domains"] = get_hosts_for_service(docker_service)
                for domain in service["domains"]:
                    self.print(darken_domain(domain))

            self.print(reset, end="")
        if service["domains"]:
            self.print()

        return service

    def process_omgeving(self, folder: str) -> ProjectDict | None:
        project: ProjectDict = {}
        hosting_domain = self.get_hostingdomain_from_env()
        self.print(
            f"{fg.brightblue}{folder}{reset}",
            f"{fg.brightyellow}{hosting_domain}",
            reset,
        )

        project["name"] = folder
        project["hostingdomain"] = hosting_domain

        if self.short:
            return None

        with self.indent():
            config = dc_config(self.ctx)
            if config is None:
                return None

            if self.du:
                usage, usage_raw = self.get_disk_usage()
                project["disk_usage_human"] = usage
                project["disk_usage_raw"] = usage_raw

            if self.settings and (settings := self.get_settings(folder)):
                project["settings"] = settings

            project["services"] = []
            for name, docker_service in config.get("services", {}).items():
                project["services"].append(self.process_docker_service(name, docker_service, hosting_domain))

        return project

    def process_compose_file(self, compose_file_path: Path) -> None:
        folder = compose_file_path.parent
        with self.ctx.cd(folder):
            if project := self.process_omgeving(str(folder)):
                self.data["projects"].append(project)

    def discover(self) -> None:
        self.reset()

        self.print(f"{bold}", self.data["server"], reset)

        compose_file_paths = self.find_compose_files()

        for compose_file in compose_file_paths:
            self.process_compose_file(Path(compose_file))

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
