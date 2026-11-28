import json
import typing as t

import pytest

from edwh.discover import Discover

WORKDIR = "/work/repo"

ACTIVE_PROJECTS = [
    {"Name": "inside", "ConfigFiles": f"{WORKDIR}/app/docker-compose.yml"},
    {"Name": "elsewhere", "ConfigFiles": "/srv/other/docker-compose.yml"},
]


class _Result:
    def __init__(self, stdout: str = "", ok: bool = True) -> None:
        self.stdout = stdout
        self.ok = ok


class FakeContext:
    """Answers the handful of shell commands discover runs, and records them."""

    def __init__(self, find_output: str = "", compose_ls: list[dict[str, str]] | None = None) -> None:
        self.find_output = find_output
        self.compose_ls = compose_ls or []
        self.commands: list[str] = []

    def run(self, command: str, **_: t.Any) -> _Result:
        self.commands.append(command)
        if command == "hostname":
            return _Result("testhost")
        if command == "pwd -P":
            return _Result(WORKDIR)
        if command.startswith("find "):
            return _Result(self.find_output)
        if "ls --format json" in command:
            return _Result(json.dumps(self.compose_ls))
        return _Result("", ok=False)


def projects(discover: Discover) -> list[str]:
    return [str(files[0]) for files in discover.find_compose_projects()]


def test_default_never_asks_docker_for_machine_projects() -> None:
    ctx = FakeContext(find_output="./docker-compose.yml\n", compose_ls=ACTIVE_PROJECTS)
    d = Discover(ctx)  # type: ignore[arg-type]

    assert projects(d) == ["docker-compose.yml"]
    assert not any("ls --format json" in c for c in ctx.commands)
    assert ctx.commands[-2].startswith("find ./docker-compose.yaml ./docker-compose.yml ./*/docker-compose.yaml")


def test_machine_includes_all_active_projects() -> None:
    ctx = FakeContext(find_output="./docker-compose.yml\n", compose_ls=ACTIVE_PROJECTS)
    d = Discover(ctx, machine=True)  # type: ignore[arg-type]

    found = projects(d)
    assert f"{WORKDIR}/app/docker-compose.yml" in found
    assert "/srv/other/docker-compose.yml" in found


def test_path_scopes_find_to_that_directory() -> None:
    ctx = FakeContext()
    Discover(ctx, path="sub dir").find_compose_projects()  # type: ignore[arg-type]

    find_cmd = next(c for c in ctx.commands if c.startswith("find "))
    assert find_cmd.startswith(
        "find 'sub dir'/docker-compose.yaml 'sub dir'/docker-compose.yml 'sub dir'/*/docker-compose.yaml"
    )


def test_path_with_machine_filters_active_projects_to_scope() -> None:
    ctx = FakeContext(compose_ls=ACTIVE_PROJECTS)
    d = Discover(ctx, machine=True, path="app")  # type: ignore[arg-type]

    found = projects(d)
    assert f"{WORKDIR}/app/docker-compose.yml" in found
    assert "/srv/other/docker-compose.yml" not in found


@pytest.mark.parametrize("path", [".", "./"])
def test_dot_path_keeps_the_repository_as_scope(path: str) -> None:
    ctx = FakeContext(compose_ls=ACTIVE_PROJECTS)
    d = Discover(ctx, machine=True, path=path)  # type: ignore[arg-type]

    found = projects(d)
    assert f"{WORKDIR}/app/docker-compose.yml" in found
    assert "/srv/other/docker-compose.yml" not in found
