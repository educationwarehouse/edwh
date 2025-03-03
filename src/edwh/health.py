import enum
import json
import sys
import typing as t
from dataclasses import dataclass

from invoke import Context
from termcolor import colored, cprint, termcolor

from .constants import DOCKER_COMPOSE, AnyDict

StatusOptions = t.Literal["created", "restarting", "running", "removing", "paused", "exited", "exited ok", "dead"]
HealthOptions = t.Literal["starting", "unhealthy", "healthy"] | None


def find_container_id(ctx: Context, container: str) -> t.Optional[str]:
    if result := ctx.run(f"{DOCKER_COMPOSE} ps -aq {container}", hide=True, warn=True):
        return result.stdout.strip()
    else:
        return None


def find_container_ids(ctx: Context, *containers: str) -> dict[str, t.Optional[str]]:
    return {container: find_container_id(ctx, container) for container in containers}


class HealthLevel(enum.IntEnum):
    # int-enum makes ordering possible

    HEALTHY = enum.auto()  # running and healthy
    RUNNING = enum.auto()  # running but health unknown
    DEGRADED = enum.auto()  # running and unhealthy
    STARTING = enum.auto()  # starting, restarting
    UNKNOWN = enum.auto()  # created
    DYING = enum.auto()  # paused or removing
    STOPPED = enum.auto()  # dead (in a good way)
    CRITICAL = enum.auto()  # dead

    @property
    def ok(self) -> bool:
        match self:
            case self.HEALTHY | self.RUNNING:
                return True
            case _:
                return False

    @property
    def color(self) -> termcolor.Color:
        match self:
            case self.HEALTHY:
                return "green"
            case self.RUNNING:
                return "cyan"
            case self.DEGRADED:
                return "yellow"
            case self.STARTING:
                return "light_yellow"
            case self.STOPPED:
                return "blue"
            case self.DYING:
                return "light_red"
            case self.CRITICAL:
                return "red"
            case _:
                # unknown
                return "grey"


@dataclass
class HealthStatus:
    container_id: str
    container: str
    status: StatusOptions
    health: HealthOptions

    @property
    def level(self) -> HealthLevel:
        """
        Return health level (lower is better).
        """
        if self.status == "exited ok":
            return HealthLevel.STOPPED
        elif self.status in {"exited", "dead"}:
            return HealthLevel.CRITICAL
        elif self.health == "healthy":
            return HealthLevel.HEALTHY
        elif self.health == "unhealthy":
            return HealthLevel.DEGRADED
        elif self.health == "starting":
            return HealthLevel.STARTING
        elif self.status == "running":
            # running but health unknown
            return HealthLevel.RUNNING
        elif self.status in {"restarting", "removing", "paused"}:
            return HealthLevel.DYING

        else:
            return HealthLevel.UNKNOWN

    @property
    def ok(self):
        return self.level.ok

    @property
    def color(self) -> termcolor.Color:
        return self.level.color

    def __repr__(self):
        return colored(f"Health({self})", self.color)

    def __str__(self):
        status = self.status
        if self.health:
            status = f"{status} & {self.health}"
        return colored(f"{self.container}: {status}", self.color)


def inspect(ctx: Context, container_id: str, *args: str) -> AnyDict | list[AnyDict]:
    """
    Docker inspect a container by ID and get the first result.

    Args:
        container_id: may be multiple (space separated)

    :raise EnvironmentError if docker inspect failed.
    """
    command = f"docker inspect {container_id}"
    if args:
        command = f"{command} {' '.join(args)}"

    # note: this assumes bash is installed and available at /usr/bin/bash,
    #  which should be fine in debian-based Linuces.
    #  this allows you to pass "`docker compose ps -aq`" as container_id
    ran = ctx.run(command, hide=True, warn=True, shell="/usr/bin/bash")

    if not ran.ok:
        cprint(f"docker inspect says: {ran.stderr}", file=sys.stderr, color="yellow")

    try:
        # even if 'ran' is falsey, it could still have valid data.
        # e.g. `docker inspect <real> <real> <fake>
        return t.cast(AnyDict, json.loads(ran.stdout))
    except json.decoder.JSONDecodeError:
        raise EnvironmentError(f"docker inspect {container_id} failed")


def get_healths(ctx: Context, *container_names: str) -> tuple[HealthStatus, ...]:
    container_ids = find_container_ids(ctx, *container_names)

    # note: use `docker inspect `docker compose ps -aq`` to prevent issues
    #  when containers die between these two statements:
    # state_by_id = {_["Id"]: _["State"] for _ in inspect(ctx, " ".join(_ for _ in container_ids.values() if _))}
    try:
        state_by_id = {_["Id"]: _["State"] for _ in inspect(ctx, "`docker compose ps -aq`")}
    except EnvironmentError:
        # probably everything down (warning is already shown by inspect() -> this can be safely ignored)
        state_by_id = {}

    def container_health(container_name: str):
        container_id = container_ids.get(container_name)
        if not (container_id and container_id in state_by_id):
            return HealthStatus(
                container_id,
                container_name,
                "dead",
                None,
            )

        state = state_by_id[container_id]
        health = state.get("Health", {})

        container_status = state.get("Status")
        health_status = health.get("Status")

        if container_status == "exited" and str(state.get("ExitCode")) == "0":
            # use exit code to know whether it was critical or not
            container_status = "exited ok"

        return HealthStatus(
            container_id,
            container_name,
            container_status,
            health_status,
        )

    return tuple(container_health(container) for container in container_names)
