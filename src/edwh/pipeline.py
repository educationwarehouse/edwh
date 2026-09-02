"""
A small step runner for multi-stage tasks, with live status reporting.

Two constraints shape the model:

1. Steps are not known up front. A pipeline decides at runtime which steps exist (how many
   services to restart, whether a snapshot needs taking), so a renderer may only draw steps that
   have actually been queued. Nothing is pre-declared.
2. There is no intra-step percentage. A step reports progress as a short status string. A shell
   step does that on stdout: a line prefixed with '::' sets the status without being logged, any
   other line is log output and also becomes the status.

Two kinds of step:

    await run.ew("setup", "setup", "--non-interactive", cwd=dst)   # an edwh task, streamed
    await run.fn("copy config", copy_config_files)                 # python, on a worker thread

A `fn` callable receives its own `Step` and must not write to stdout: the renderer owns the
terminal while the run is live. Use `step.report(...)` instead, and pass `hide=True` to any
`ctx.run` it performs.
"""

import asyncio
import contextlib
import os
import time
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

from .helpers import ew_command

T_State = t.Literal["queued", "running", "done", "failed", "skipped"]

DEFAULT_MAX_PARALLEL = 4


@dataclass
class Step:
    name: str
    group: int
    state: T_State = "queued"
    status: str = ""
    started: float = 0.0
    ended: float = 0.0
    lines: list[str] = field(default_factory=list)
    out: str = ""  # full stdout of a shell step, for runtime decisions
    error: BaseException | None = None

    # called after every state or status change, with this step: on_change=lambda step: ...
    on_change: t.Callable[["Step"], None] = field(default=lambda _: None, repr=False)

    @property
    def elapsed(self) -> float:
        if not self.started:
            return 0.0
        return (self.ended or time.perf_counter()) - self.started

    @property
    def active(self) -> bool:
        return self.state in ("queued", "running")

    @property
    def ok(self) -> bool:
        return self.state in ("done", "skipped")

    def report(self, status: str) -> None:
        """Set the status text shown next to this step. Safe to call from a worker thread."""
        self.status = status
        self.on_change(self)

    def log(self, line: str) -> None:
        """Record a line of output and show it as the current status."""
        self.lines.append(line)
        self.report(line)


class StepFailedError(Exception):
    """Raised by Run.check() when a step did not succeed."""


class Run:
    """Registry of the steps that exist *so far*. Renderers read `self.steps`."""

    def __init__(self, max_parallel: int = DEFAULT_MAX_PARALLEL) -> None:
        self.steps: list[Step] = []
        self.on_change: t.Callable[[], None] = lambda: None
        self.group = 0
        self.done = False
        self.started = time.perf_counter()
        self.max_parallel = max_parallel

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started

    @property
    def failed(self) -> list[Step]:
        return [step for step in self.steps if step.state == "failed"]

    def groups(self) -> list[list[Step]]:
        """Queued steps bundled per parallel group, in submission order."""
        out: list[list[Step]] = []
        for step in self.steps:
            if not out or out[-1][0].group != step.group:
                out.append([step])
            else:
                out[-1].append(step)
        return out

    def check(self) -> None:
        """Raise if any step has failed so far. Call between phases that depend on each other."""
        if failures := self.failed:
            first = failures[0]
            raise StepFailedError(f"{first.name}: {first.status}") from first.error

    # -- queueing -------------------------------------------------------------------------

    def _queue(self, names: t.Iterable[str]) -> list[Step]:
        self.group += 1
        steps = [Step(name, self.group, on_change=lambda _: self.on_change()) for name in names]
        self.steps.extend(steps)
        self.on_change()
        return steps

    async def _gather(self, work: list[t.Coroutine[t.Any, t.Any, None]]) -> None:
        gate = asyncio.Semaphore(self.max_parallel)

        async def guarded(coro: t.Coroutine[t.Any, t.Any, None]) -> None:
            async with gate:
                await coro

        await asyncio.gather(*(guarded(item) for item in work))

    async def sh(self, name: str, cmd: str, cwd: str | Path | None = None, env: dict[str, str] | None = None) -> Step:
        """Run one shell command as a step, streaming its output into the status line."""
        return (await self.shell_group([(name, cmd)], cwd=cwd, env=env))[0]

    async def shell_group(
        self,
        specs: list[tuple[str, str]],
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
    ) -> list[Step]:
        """Queue and run several shell commands, at most `max_parallel` at a time."""
        steps = self._queue(name for name, _ in specs)
        await self._gather([self._exec(step, cmd, cwd, env) for step, (_, cmd) in zip(steps, specs)])
        return steps

    async def ew(self, name: str, *args: str, cwd: str | Path | None = None, env: dict[str, str] | None = None) -> Step:
        """Run an edwh task as a step, through the same edwh that is running."""
        return await self.sh(name, f"{ew_command()} {' '.join(args)}", cwd=cwd, env=env)

    async def fn(self, name: str, func: t.Callable[[Step], t.Any]) -> Step:
        """Run a python callable as a step, on a worker thread so the renderer keeps ticking."""
        return (await self.fn_group([(name, func)]))[0]

    async def fn_group(self, specs: list[tuple[str, t.Callable[[Step], t.Any]]]) -> list[Step]:
        steps = self._queue(name for name, _ in specs)
        await self._gather([self._call(step, func) for step, (_, func) in zip(steps, specs)])
        return steps

    def skip(self, name: str, reason: str = "skipped") -> Step:
        """Record a step that was deliberately not run, so the reason stays visible."""
        step = self._queue([name])[0]
        step.state = "skipped"
        step.status = reason
        self.on_change()
        return step

    # -- execution ------------------------------------------------------------------------

    def _start(self, step: Step) -> None:
        step.state = "running"
        step.started = time.perf_counter()
        step.status = "starting"
        self.on_change()

    def _finish(self, step: Step, state: T_State, status: str = "") -> None:
        step.ended = time.perf_counter()
        step.state = state
        if status:
            step.status = status
        elif not step.status or step.status == "starting":
            step.status = "ok" if state == "done" else state
        self.on_change()

    async def _exec(self, step: Step, cmd: str, cwd: str | Path | None, env: dict[str, str] | None) -> None:
        self._start(step)

        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=str(cwd) if cwd else None,
                env={**os.environ, **env} if env else None,
            )
        except OSError as e:
            step.error = e
            self._finish(step, "failed", str(e))
            return

        # stdout is a pipe, so this is set; a command that prints nothing simply yields no lines
        if proc.stdout:
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").rstrip()
                step.out += line + "\n"
                if line.startswith("::"):
                    step.status = line[2:].strip()
                    self.on_change()
                elif line:
                    step.log(line)

        rc = await proc.wait()
        self._finish(step, "done" if rc == 0 else "failed", f"exit {rc}" if rc else "")

    async def _call(self, step: Step, func: t.Callable[[Step], t.Any]) -> None:
        self._start(step)
        try:
            await asyncio.to_thread(func, step)
        except Exception as e:
            # one failing step must not tear down the rest of the group
            step.error = e
            self._finish(step, "failed", f"{type(e).__name__}: {e}")
        else:
            self._finish(step, "done")


T_Render = t.Callable[[Run], None]


async def drive(
    pipeline: t.Callable[[Run], t.Awaitable[t.Any]],
    render: T_Render,
    interval: float = 1 / 20,
    max_parallel: int = DEFAULT_MAX_PARALLEL,
) -> Run:
    """Run `pipeline`, redrawing at a fixed framerate. Returns the Run, even if it failed."""
    run = Run(max_parallel=max_parallel)
    run.on_change = lambda: None  # the ticker drives redraws; per-event redraws would thrash
    stop = asyncio.Event()

    async def ticker() -> None:
        while not stop.is_set():
            render(run)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), interval)
        run.done = True
        render(run)

    ticking = asyncio.create_task(ticker())
    try:
        await pipeline(run)
    except StepFailedError:
        pass  # already visible in the step states; the caller inspects run.failed
    finally:
        stop.set()
        await ticking

    return run
