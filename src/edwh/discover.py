import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

import humanize
from ansi.color import fg
from ansi.color.fx import bold, reset
from invoke import Context

from .helpers import dc_config, dump_set_as_list, noop


def indent(text, prefix="  "):
    return prefix + text


def dedent(text, prefix="  "):
    return text.replace(prefix, "", 1)


HOST_RE = re.compile(r"`(.*?)`")


def strip_host(s: str) -> str:
    return HOST_RE.findall(s.strip())[0]


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
    settings: dict
    services: list[ServiceDict]


class DataDict(TypedDict):
    server: str
    projects: list[ProjectDict]


def get_hosts_for_service(docker_service: dict) -> set[str]:
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
        du=False,
        exposes=False,
        ports=False,
        host_labels=True,
        short=False,
        settings=False,
        as_json=False,
    ):
        self.ctx = ctx
        self.du = du
        self.exposes = exposes
        self.ports = ports
        self.host_labels = host_labels
        self.short = short
        self.settings = settings
        self.as_json = as_json

        self.print_fn = noop if as_json else print
        self.reset()

    def reset(self):
        hostname = self.find_hostname()

        self.i = ""
        self.data = {
            "server": hostname,
            "projects": [],
        }

    @contextmanager
    def indent(self, prefix="  "):
        # context manager
        self.i = indent(self.i, prefix)
        yield
        self.i = dedent(self.i, prefix)

    def print(self, *args, **kwargs):
        self.print_fn(self.i, *args, **kwargs)

    def get_hostingdomain_from_env(self) -> str:
        hosting_domain = self.ctx.run("cat .env | grep HOSTINGDOMAIN", echo=False, hide=True, warn=True).stdout.strip()
        return hosting_domain.strip().split("=")[-1] if hosting_domain else ""

    def find_compose_files(self) -> list[str]:
        return (
            self.ctx.run(
                "find */docker-compose.yaml */docker-compose.yml",
                echo=False,
                hide=True,
                warn=True,
            )
            .stdout.strip()
            .split("\n")
        )

    def find_hostname(self) -> str:
        return self.ctx.run("hostname", hide=True).stdout.strip()

    def get_disk_usage(self) -> tuple[str, int]:
        usage_raw = self.ctx.run("du -sh . --block-size=1", echo=False, hide=True).stdout.strip().split("\t")[0]
        usage = humanize.naturalsize(usage_raw, binary=True)
        self.print(f"{fg.boldred}Disk usage: {usage}{reset}")

        return usage, int(usage_raw)

    def get_settings(self, folder: str):
        json_flag = "--json" if self.as_json else ""
        settings_output = self.ctx.run(f"~/.local/bin/edwh settings {json_flag}", echo=False, hide=True).stdout.strip()

        if self.as_json:
            try:
                return json.loads(settings_output)
            except json.JSONDecodeError:
                print(f"Error loading settings for {self.data['server']}/{folder}", file=sys.stderr)
        else:
            self.print(f"{fg.boldred}Settings:", reset)
            with self.indent():
                for line in settings_output.split("\n"):
                    self.print(line)

    def process_docker_service(self, name: str, docker_service: dict, hosting_domain: str):
        service = {"name": name}

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

    def process_omgeving(self, folder: str):
        project = {}
        hosting_domain = self.get_hostingdomain_from_env()
        self.print(
            f"{fg.brightblue}{folder}{reset}",
            f"{fg.brightyellow}{hosting_domain}",
            reset,
        )

        project["name"] = folder
        project["hostingdomain"] = hosting_domain

        if self.short:
            return

        with self.indent():
            config = dc_config(self.ctx)
            if config is None:
                return

            if self.du:
                usage, usage_raw = self.get_disk_usage()
                project["disk_usage_human"] = usage
                project["disk_usage_raw"] = usage_raw

            if self.settings:
                project["settings"] = self.get_settings(folder)

            project["services"] = []
            for name, docker_service in config.get("services", {}).items():
                project["services"].append(self.process_docker_service(name, docker_service, hosting_domain))

        return project

    def process_compose_file(self, compose_file_path: Path):
        folder = compose_file_path.parent
        with self.ctx.cd(folder):
            self.data["projects"].append(self.process_omgeving(str(folder)))

    def discover(self):
        self.reset()

        self.print(f"{bold}", self.data["server"], reset)

        compose_file_paths = self.find_compose_files()

        for compose_file in compose_file_paths:
            self.process_compose_file(Path(compose_file))

        if self.as_json:
            print(json.dumps({"data": self.data}, indent=2, default=dump_set_as_list))


def discover(
    ctx: Context,
    du=False,
    exposes=False,
    ports=False,
    host_labels=True,
    short=False,
    settings=False,
    as_json=False,
):
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
