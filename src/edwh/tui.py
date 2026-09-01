"""
Renderers for `edwh.pipeline`.

`lane_board` draws a live board: one row per queued step, spinner on what is running, a dim
marker on what is waiting behind the concurrency limit, and whatever status text the step last
reported on the right. `plain` writes one line per state transition instead, for pipes, CI and
`--no-tui`.

Pick with `renderer_for(title)`; it falls back to `plain` when stdout is not a terminal.
"""

import sys
import typing as t
from contextlib import contextmanager

from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from .pipeline import Run, Step, T_Render

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
GLYPH: dict[str, tuple[str, str]] = {
    "queued": ("◦", "grey35"),
    "done": ("✔", "green"),
    "failed": ("✘", "red"),
    "skipped": ("-", "grey35"),
}
STATUS_WIDTH = 40
NAME_WIDTH = 26


def _row(step: Step, tick: int, branch: str) -> Text:
    if step.state == "running":
        mark, colour = FRAMES[tick % len(FRAMES)], "cyan"
    else:
        mark, colour = GLYPH[step.state]

    line = Text()
    line.append(f" {branch}", style="grey35")
    line.append(f"{mark} ", style=colour)
    line.append(step.name[:NAME_WIDTH].ljust(NAME_WIDTH), style="bold" if step.state == "running" else "")
    line.append(f"{step.status[:STATUS_WIDTH]:<{STATUS_WIDTH}}", style="red" if step.state == "failed" else "grey42")
    line.append(f"{step.elapsed:5.1f}s" if step.started else "      ", style="grey50")
    return line


def _board(run: Run, tick: int) -> Group:
    rows: list[Text] = []
    for group in run.groups():
        parallel = len(group) > 1
        for i, step in enumerate(group):
            branch = ("└─ " if i == len(group) - 1 else "├─ ") if parallel else "   "
            rows.append(_row(step, tick, branch))

    if not run.done:
        # the pipeline may still add steps we cannot name yet
        rows.append(Text("    ⋮", style="grey30"))

    return Group(*rows)


@contextmanager
def lane_board(title: str = "") -> t.Iterator[T_Render]:
    """Live multi-row board. Owns the terminal for its duration: do not print inside."""
    console = Console()
    if title:
        console.print(f"[bold]{title}[/bold]\n")

    tick = 0

    with Live(console=console, refresh_per_second=20) as live:

        def render(run: Run) -> None:
            nonlocal tick
            tick += 1
            live.update(_board(run, tick))

        yield render


@contextmanager
def plain(title: str = "") -> t.Iterator[T_Render]:
    """One line per state transition. No cursor movement, safe for pipes and CI."""
    if title:
        print(title)

    seen: dict[int, str] = {}

    def render(run: Run) -> None:
        for step in run.steps:
            if step.state == "running" or seen.get(id(step)) == step.state:
                continue
            seen[id(step)] = step.state
            if step.state == "queued":
                continue
            mark = {"done": "ok", "failed": "FAIL", "skipped": "skip"}[step.state]
            print(f"[{mark:>4}] {step.name} - {step.status} ({step.elapsed:.1f}s)")

    yield render


def renderer_for(title: str = "", tui: bool = True) -> t.ContextManager[T_Render]:
    """The lane board when a terminal is available and wanted, plain output otherwise."""
    if tui and sys.stdout.isatty():
        return lane_board(title)
    return plain(title)
