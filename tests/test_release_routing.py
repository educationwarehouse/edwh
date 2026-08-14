# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT
"""
How plugin.release and plugin.bump choose, and refuse, a release backend.

Routing depends on three things the project file cannot answer: whether vommit
is importable, what the user replies, and what a shell-out would do. Each is
stood in for at its own boundary -- the import system, stdin, `Context.run` --
so what runs here is the real routing code, not a version of it with its
collaborators swapped out.
"""

import importlib
import io
import sys
import types
import typing as t
from contextlib import chdir, contextmanager
from pathlib import Path

import ewok
import pytest

from src.edwh.local_tasks import plugin

# What the `project` fixture hands back: write this pyproject, get its directory.
type MakeProject = t.Callable[[str], Path]


class Answers(t.Protocol):
    """
    What the `answers` fixture hands back.

    A Protocol rather than a Callable alias because the keystrokes are
    variadic, which `Callable[...]` can only spell as "any arguments at all".
    """

    def __call__(self, *keystrokes: str) -> t.ContextManager[None]: ...


VOMMIT = """[project]
name = "demo"
version = "1.0.0"

[tool.vommit]
prerelease_token = "beta"
"""

BARE = """[project]
name = "demo"
version = "1.0.0"
"""


class RecordingContext(ewok.Context):
    """
    A Context that writes commands down instead of running them.

    Every side effect on this path leaves through `Context.run`: installing
    vommit, invoking python-semantic-release, publishing. So an empty
    `commands` is the proof that none of it happened -- and the real Context
    would SSH to localhost to find that out.
    """

    def __init__(self) -> None:
        super().__init__(host="localhost")
        self.commands: list[str] = []

    def run(self, command: str, **_: t.Any) -> None:  # type: ignore[override]
        self.commands.append(command)
        return None


@pytest.fixture
def ctx() -> RecordingContext:
    return RecordingContext()


@pytest.fixture
def project(tmp_path: Path) -> MakeProject:
    """Build a throwaway project to run a task inside."""

    def make(content: str) -> Path:
        (tmp_path / "pyproject.toml").write_text(content)
        return tmp_path

    return make


@pytest.fixture
def no_vommit() -> t.Iterator[None]:
    """
    An interpreter where the optional `vommit` extra is not installed.

    Blocked at the import system rather than at `vommit_tasks`, because the
    ImportError is the thing under test: [tool.vommit] in a pyproject outlives
    the install that wrote it, so the routing has to survive a real one.
    """

    class Blocked:
        def find_spec(
            self, fullname: str, _path: t.Sequence[str] | None = None, _target: types.ModuleType | None = None
        ) -> None:
            if fullname.split(".")[0] == "vommit":
                raise ImportError("No module named 'vommit'")
            return None

    # an already-imported vommit would never reach the finder
    imported = {name: module for name, module in sys.modules.items() if name.split(".")[0] == "vommit"}
    for name in imported:
        del sys.modules[name]

    finder = Blocked()
    sys.meta_path.insert(0, finder)
    importlib.invalidate_caches()
    try:
        yield
    finally:
        sys.meta_path.remove(finder)
        sys.modules.update(imported)


class Unattended(io.StringIO):
    """
    A stdin with nobody behind it: not a terminal, and loud when read.

    pytest only hides the real stdin while it captures, so under `-s` the
    terminal is still attached, `_can_ask` sees a tty, and any test that
    reaches a prompt sits there waiting for a human. This fails instead.
    """

    def isatty(self) -> bool:
        return False

    def readline(self, *_args: t.Any) -> str:  # type: ignore[override]  # what input() calls
        raise AssertionError("a prompt was reached that this test does not answer")


@contextmanager
def _stdin(replacement: io.StringIO) -> t.Iterator[None]:
    original, sys.stdin = sys.stdin, replacement
    try:
        yield
    finally:
        sys.stdin = original


@pytest.fixture(autouse=True)
def unattended() -> t.Iterator[None]:
    """Nobody is at the keyboard for any test in here, `-s` or not."""
    with _stdin(Unattended()):
        yield


@pytest.fixture
def answers() -> Answers:
    """
    Type answers into the prompts, as somebody at a terminal would.

    Only the prompts a test names: anything else it is asked fails it, because
    `unattended` is still what the answers run out into.
    """

    def typed(*keystrokes: str) -> t.ContextManager[None]:
        return _stdin(io.StringIO("".join(f"{key}\n" for key in keystrokes)))

    return typed


@pytest.mark.usefixtures("no_vommit")
def test_configured_for_vommit_but_not_installed_offers_the_install(
    project: MakeProject, ctx: RecordingContext, answers: Answers, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    vommit's config outlives its install -- a migrated project cloned onto a
    second machine has [tool.vommit] and no vommit. That has to reach the
    install offer, not an assertion.
    """
    with chdir(project(VOMMIT)), answers("n"):
        assert plugin._resolve_backend(ctx) is None

    printed = capsys.readouterr().out
    assert "configured for vommit, but vommit is not installed" in printed, "the diagnosis was never printed"
    assert "Install vommit" in printed, "no install was offered"
    assert plugin.vommit_specifier() in printed, "the offer did not name the supported range"
    assert not ctx.commands, f"declining still ran {ctx.commands}"


@pytest.mark.usefixtures("no_vommit")
def test_declining_that_install_does_not_release(project: MakeProject, ctx: RecordingContext, answers: Answers) -> None:
    """Refusing the install must stop, not fall back to the deprecated path."""
    with chdir(project(VOMMIT)), answers("n", "n"):
        plugin.release(ctx, noop=True, pull=False)
        # ewok hands back its own empty result rather than None, so this asserts
        # no version came out
        assert not plugin.bump(ctx, noop=True)

    # semantic-release, uv build and uv publish would all show up here
    assert not ctx.commands, f"reached the shell anyway: {ctx.commands}"


@pytest.mark.usefixtures("no_vommit")
def test_accepting_the_install_installs_the_declared_spec(
    project: MakeProject, ctx: RecordingContext, answers: Answers, capsys: pytest.CaptureFixture[str]
) -> None:
    """
    Accepting installs into edwh's own environment -- that is what activates
    vommit's `edwh` entry point -- and then stops, because this interpreter
    cannot import what a subprocess just installed.
    """
    with chdir(project(VOMMIT)), answers("y"):
        assert plugin._resolve_backend(ctx) is None

    assert len(ctx.commands) == 1, f"expected one install, got {ctx.commands}"
    assert " install " in ctx.commands[0], f"{ctx.commands[0]} is not an install"
    assert plugin._vommit_spec() in ctx.commands[0], "installed something other than the pinned spec"
    assert "run this command again" in capsys.readouterr().out, "no way out was offered"


def test_installed_vommit_resolves_without_asking(project: MakeProject, ctx: RecordingContext) -> None:
    """
    The ordinary case: config and install agree, so nothing is asked and
    nothing is run -- reading stdin at all would fail this test.
    """
    pytest.importorskip("vommit.tasks")

    with chdir(project(VOMMIT)):
        assert plugin._resolve_backend(ctx) == "vommit"

    assert not ctx.commands


def test_bump_without_any_backend_does_not_reach_psr(project: MakeProject, ctx: RecordingContext) -> None:
    """
    `release` already refused this; `bump` used to install psr and run it
    against a project that has no psr config.

    Nothing is asked either: `_can_ask` checks for a terminal before offering
    the vommit setup, and `unattended` is not one.
    """
    with chdir(project(BARE)):
        assert not plugin.bump(ctx, noop=True)

    assert not ctx.commands, f"reached the shell anyway: {ctx.commands}"


def test_install_specifier_carries_the_declared_bound() -> None:
    """
    The install prompt must not be able to pull a vommit edwh does not support.
    """
    specifier = plugin.vommit_specifier()

    assert specifier, "no version bound at all"
    assert "<1" in specifier.replace(" ", "")
    assert plugin._vommit_spec().startswith("vommit")
    assert plugin._vommit_spec().endswith(specifier)


@pytest.mark.usefixtures("no_vommit")
def test_require_vommit_task_keeps_its_result_to_itself(ctx: RecordingContext, answers: Answers) -> None:
    """
    ewok writes a task's return value into the shared ctx["result"], which the
    enclosing task then returns as its own. `ensure_vommit` is a plain function
    for that reason; the task wrapper must not reintroduce the leak.
    """
    with answers("n"):
        plugin.require_vommit(ctx)

    assert not ctx["result"], f"leaked {ctx['result']!r} into the shared result"
