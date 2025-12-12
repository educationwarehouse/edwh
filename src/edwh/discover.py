import contextlib
import json
import re
import sys
import typing as t
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

import humanize
from invoke.context import Context
from termcolor import colored, cprint

from .helpers import AnyDict, dc_config, dump_set_as_list, noop


def indent(text: str, prefix: str = "  ") -> str:
    return prefix + text


def dedent(text: str, prefix: str = "  ") -> str:
    return text.replace(prefix, "", 1)


def terminal_link(url: str, text: str = None) -> str:
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
    current_indent: str
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

        self.current_indent = ""
        self.data = {
            "server": hostname,
            "projects": [],
        }

    @contextmanager
    def indent(self, prefix: str = "  ") -> t.Generator[None, None, None]:
        self.current_indent = indent(self.current_indent, prefix)
        yield
        self.current_indent = dedent(self.current_indent, prefix)

    def print(self, *args: t.Any, **kwargs: t.Any) -> None:
        sep = kwargs.pop("sep", " ")
        msg = sep.join([self.current_indent, *args])
        self.print_fn(msg, **kwargs)

    def get_hostingdomain_from_env(self) -> str:
        if result := self.ctx.run(
            "grep HOSTINGDOMAIN .env",
            echo=False,
            hide=True,
            warn=True,
        ):
            hosting_domain = result.stdout.strip()
            return hosting_domain.strip().split("=")[-1]
        else:
            return ""

    def find_hostname(self) -> str:
        if result := self.ctx.run("hostname", hide=True):
            return result.stdout.strip()
        else:
            return ""

    def get_compose_config(self) -> AnyDict:
        """Get merged docker compose config."""
        return dc_config(self.ctx) or None

    def find_project_folders(self) -> t.Generator[Path, None, None]:
        """
        Find folders containing docker-compose projects.

        Searches for directories up to 2 levels deep and tests each one
        by running `docker compose config` to detect valid projects.
        Works regardless of docker-compose file naming conventions since
        it relies on the docker-compose command itself rather than file patterns.

        Yields:
            Path objects for directories with valid docker-compose projects.
        """
        # Find all directories at the current level (usually home)
        result = self.ctx.run(
            "find . -maxdepth 1 -type d",
            echo=False,
            hide=True,
            warn=True,
        )
        candidates = (
            Path(candidate) for candidate in result.stdout.strip().split("\n") if candidate and candidate != "."
        )

        # Test each directory to see if it has a docker-compose project
        for candidate in candidates:
            with contextlib.suppress(Exception), self.ctx.cd(candidate):
                if self.get_compose_config():
                    yield candidate

    def get_disk_usage(self) -> tuple[str, int]:
        if result := self.ctx.run(
            "du -sh . --block-size=1",
            echo=False,
            hide=True,
        ):
            usage_raw = result.stdout.strip().split("\t")[0]
            usage = humanize.naturalsize(usage_raw, binary=True)
            self.print(
                f"Disk usage: {usage}",
                color="red",
                attrs=["bold"],
            )

            return usage, int(usage_raw)
        else:
            raise EnvironmentError("Failed running `du`")

    def get_settings(self, folder: str) -> AnyDict | None:
        json_flag = "--json" if self.as_json else ""
        if result := self.ctx.run(
            f"~/.local/bin/edwh settings {json_flag}",
            echo=False,
            hide=True,
        ):
            settings_output = result.stdout.strip()
        else:
            settings_output = ""

        if self.as_json:
            try:
                return t.cast(
                    AnyDict,
                    json.loads(settings_output),
                )
            except json.JSONDecodeError:
                print(
                    f"Error loading settings for {self.data['server']}/{folder}",
                    file=sys.stderr,
                )
        else:
            self.print("Settings:", color="red", attrs=["bold"])
            with self.indent():
                for line in settings_output.split("\n"):
                    self.print(line)
        return None

    def process_docker_service(
        self,
        name: str,
        docker_service: AnyDict,
        hosting_domain: str,
    ) -> ServiceDict:
        service: ServiceDict = {"name": name}
        if not self.short:
            self.print(name, color="green")
        with self.indent():
            if self.exposes and not self.short:
                if exposed_ports := docker_service.get("expose", []):
                    self.print(
                        f"Exposes: {', '.join([str(port) for port in exposed_ports])}",
                        color="red",
                        attrs=["bold"],
                    )
                service["exposes"] = exposed_ports
            if self.ports:
                if port_list := docker_service.get("ports", []):
                    self.print(
                        f"Ports: {', '.join([str(port) for port in port_list]) if port_list else ''}",
                        color="red",
                        attrs=["bold"],
                    )
                service["ports"] = port_list

            service["domains"] = set()
            if self.host_labels and not self.short:
                service["domains"] = get_hosts_for_service(docker_service)
                for domain in service["domains"]:
                    self.print(
                        terminal_link(
                            f"https://{domain}",
                            domain.replace(
                                hosting_domain,
                                colored(
                                    hosting_domain,
                                    color="dark_grey",
                                ),
                            ),
                        ),
                    )

        if service["domains"]:
            self.print()

        return service

    def process_omgeving(self, folder: str) -> ProjectDict | None:
        project: ProjectDict = {}
        hosting_domain = self.get_hostingdomain_from_env()
        self.print(
            colored(folder, color="light_blue"),
            colored(hosting_domain, color="light_yellow"),
        )

        project["name"] = folder
        project["hostingdomain"] = hosting_domain

        with self.indent():
            compose_config = self.get_compose_config()
            if not compose_config:
                return None

            if self.du and not self.short:
                usage, usage_raw = self.get_disk_usage()
                project["disk_usage_human"] = usage
                project["disk_usage_raw"] = usage_raw

            if self.settings and (settings := self.get_settings(folder)) and not self.short:
                project["settings"] = settings

            project["services"] = []
            for name, docker_service in compose_config.get(
                "services",
                {},
            ).items():
                project["services"].append(
                    self.process_docker_service(
                        name,
                        docker_service,
                        hosting_domain,
                    )
                )

        return project

    def discover(self) -> None:
        self.reset()

        self.print(self.data["server"], attrs=["bold"])

        for folder in self.find_project_folders():
            with self.ctx.cd(folder):
                if project := self.process_omgeving(str(folder)):
                    self.data["projects"].append(project)

        if self.as_json:
            print(
                json.dumps(
                    {"data": self.data},
                    indent=2,
                    default=dump_set_as_list,
                )
            )


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
