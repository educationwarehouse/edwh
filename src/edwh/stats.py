"""A scrollable, filterable live view of Docker container statistics."""

import json
import os
import re
import select
import shutil
import sys
import threading
import typing as t
from contextlib import contextmanager
from dataclasses import dataclass, field

from click._termui_impl import raw_terminal
from ewok import Context
from rich.console import Console, Group
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .helpers import KEY_ARROWDOWN, KEY_ARROWUP, viewport

STATS_COMMAND = "docker stats --no-stream --format '{{json .}}'"
NUMBER_PATTERN = re.compile(r"\s*([\d.]+)\s*([A-Za-z]*)")
KEY_PAGE_UP = "\x1b[5~"
KEY_PAGE_DOWN = "\x1b[6~"
KEY_ARROW_LEFT = "\x1b[D"
KEY_ARROW_RIGHT = "\x1b[C"
KEY_ESCAPE = "\x1b"
KEY_INTERRUPT = "\x03"
KEY_BACKSPACE = ("\x7f", "\b")
KEY_ENTER = ("\r", "\n")
KEY_SEQUENCES = re.compile(r"\x1b\[[0-9;]*[A-Za-z~]|\x1bO[A-Za-z]|\x1b|[^\x1b]")
INCOMPLETE_KEY = re.compile(r"\x1b(?:\[[0-9;]*|O)?$")
COLUMNS = (
    ("Name", "Name"),
    ("CPU %", "CPUPerc"),
    ("Mem usage / limit", "MemUsage"),
    ("Mem %", "MemPerc"),
    ("Net I/O", "NetIO"),
    ("Block I/O", "BlockIO"),
    ("PIDs", "PIDs"),
)
COLUMN_WIDTHS = (24, 9, 21, 9, 19, 19, 8)
COMPACT_WIDTHS = (21, 9, 21, 9, 19, 19, 8)
COMPACT_COLUMNS = (0, 1, 2, 3, 6)
IO_COLUMNS = (0, 4, 5)
FULL_TABLE_WIDTH = sum(COLUMN_WIDTHS) + 3 * (len(COLUMNS) - 1)
SIZE_MULTIPLIERS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
}


class TerminalOutput(t.TextIO):
    """Keep Rich's line breaks aligned while Click reads in raw mode."""

    def __init__(self, stream: t.TextIO) -> None:
        self.stream = stream

    def write(self, value: str) -> int:
        self.stream.write(value.replace("\n", "\r\n"))
        return len(value)

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        return self.stream.isatty()

    @property
    def encoding(self) -> str:
        return self.stream.encoding


@contextmanager
def _keyboard_input() -> t.Iterator[t.Callable[[], list[str]]]:
    """Expose complete keys while keeping raw mode and ANSI parsing together."""
    with raw_terminal() as fd:
        pending = ""

        def read_keys() -> list[str]:
            nonlocal pending
            pending += os.read(fd, 32).decode(sys.stdin.encoding or "utf-8", "replace")
            if KEY_INTERRUPT in pending:
                raise KeyboardInterrupt

            incomplete = INCOMPLETE_KEY.search(pending)
            if incomplete:
                ready, pending = pending[: incomplete.start()], pending[incomplete.start() :]
                if pending == KEY_ESCAPE and not select.select([fd], [], [], 0.05)[0]:
                    ready, pending = ready + pending, ""
            else:
                ready, pending = pending, ""
            return KEY_SEQUENCES.findall(ready)

        yield read_keys


def _key_action(key: str, filtering: bool) -> tuple[str, str]:
    """Translate terminal keys into actions for the stats view."""
    if key in ("q", "Q") and not filtering:
        return "quit", ""
    elif key in "1234567" and not filtering:
        return "sort", key
    elif key in (KEY_ARROWUP, "k") and not filtering:
        return "up", ""
    elif key in (KEY_ARROWDOWN, "j") and not filtering:
        return "down", ""
    elif key == KEY_PAGE_UP and not filtering:
        return "page_up", ""
    elif key == KEY_PAGE_DOWN and not filtering:
        return "page_down", ""
    elif key == "/" and not filtering:
        return "start_filter", ""
    elif key in ("i", "I") and not filtering:
        return "toggle_io", ""
    elif key == KEY_ARROW_LEFT and not filtering:
        return "core_columns", ""
    elif key == KEY_ARROW_RIGHT and not filtering:
        return "io_columns", ""
    elif key == KEY_ESCAPE:
        return "clear_filter", ""
    elif key in KEY_BACKSPACE and filtering:
        return "backspace", ""
    elif key in KEY_ENTER and filtering:
        return "finish_filter", ""
    elif filtering and key.isprintable():
        return "append_filter", key
    else:
        return "ignore", ""


def _fetch(ctx: Context) -> list[dict[str, str]]:
    result = ctx.run(STATS_COMMAND, hide=True, echo=False, warn=True, in_stream=False)
    if result is None or not result.ok:
        detail = result.stderr.strip() if result is not None else ""
        raise RuntimeError(detail or "docker stats failed")
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def _poll(
    ctx: Context,
    update: t.Callable[[list[dict[str, str]] | None, str], None],
    stop: threading.Event,
) -> None:
    while not stop.is_set():
        try:
            update(_fetch(ctx), "")
        except (OSError, RuntimeError, ValueError) as exc:
            update(None, str(exc))
            return
        stop.wait(2)


def _sort_value(row: dict[str, str], column: int) -> str | float:
    value = str(row.get(COLUMNS[column][1], ""))
    if column == 0:
        return value.casefold()
    number = NUMBER_PATTERN.match(value)
    if number is None:
        return -1.0
    return float(number[1]) * SIZE_MULTIPLIERS.get(number[2], 1)


def _row_values(row: dict[str, str]) -> list[str]:
    return [str(row.get(key, "")) for _, key in COLUMNS]


@dataclass
class StatsState:
    rows: list[dict[str, str]] = field(default_factory=list)
    query: str = ""
    cursor: int = 0
    filtering: bool = False
    message: str = "Loading…"
    sort_column: int = 0
    descending: bool = False
    show_io: bool = False

    def visible_count(self) -> int:
        return sum(self.query.casefold() in row.get("Name", "").casefold() for row in self.rows)


def _frame(state: StatsState) -> Group:
    visible = [row for row in state.rows if state.query.casefold() in row.get("Name", "").casefold()]
    height = max(shutil.get_terminal_size().lines - 5, 1)
    start, stop = viewport(len(visible), state.cursor, height)

    terminal_width = shutil.get_terminal_size().columns
    compact = terminal_width < FULL_TABLE_WIDTH
    columns = IO_COLUMNS if compact and state.show_io else COMPACT_COLUMNS if compact else range(len(COLUMNS))
    table = Table(expand=True, show_edge=False, pad_edge=False)
    for index in columns:
        title = COLUMNS[index][0]
        marker = " ▼" if state.descending else " ▲"
        label = f"{index + 1} {title}"
        table.add_column(
            label + marker if index == state.sort_column else label,
            no_wrap=True,
            overflow="ellipsis",
            width=(COMPACT_WIDTHS if compact else COLUMN_WIDTHS)[index],
        )
    for index, row in enumerate(visible[start:stop], start=start):
        values = _row_values(row)
        table.add_row(*(values[column] for column in columns), style="reverse" if index == state.cursor else None)

    heading = Text(f"Docker stats  {len(visible)}/{len(state.rows)} containers", style="bold")
    status = Text(f"Filter: {state.query}{'_' if state.filtering else ''}  |  {state.message}")
    keys = Text("↑/↓ or j/k scroll  PgUp/PgDn page  1-7 sort  / filter  Esc clear  q quit", style="dim")
    if compact:
        keys = Text("↑/↓ scroll  PgUp/PgDn page  ←/→ or i columns  1-7 sort  / filter  q quit", style="dim")
    return Group(heading, status, table, keys)


def show_stats(ctx: Context) -> None:
    """Display Docker stats, falling back to a snapshot without a terminal."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        rows = sorted(_fetch(ctx), key=lambda row: row.get("Name", "").casefold())
        console = Console()
        table = Table()
        for title, _ in COLUMNS:
            table.add_column(title)
        for row in rows:
            table.add_row(*_row_values(row))
        console.print(table)
        return

    stop = threading.Event()
    lock = threading.Lock()
    state = StatsState()

    with Live(screen=True, refresh_per_second=2, console=Console(file=TerminalOutput(sys.stdout))) as live:

        def render(refresh: bool = False) -> None:
            live.update(_frame(state), refresh=refresh)

        def on_update(data: list[dict[str, str]] | None, error: str) -> None:
            with lock:
                if stop.is_set():
                    return
                if error:
                    state.message = error
                elif data is not None:
                    state.rows = sorted(
                        data, key=lambda row: _sort_value(row, state.sort_column), reverse=state.descending
                    )
                    state.message = "Updated"
                state.cursor = min(state.cursor, max(state.visible_count() - 1, 0))
                render()

        render(refresh=True)
        poller = threading.Thread(target=_poll, args=(ctx, on_update, stop), daemon=True)
        poller.start()
        try:
            with _keyboard_input() as read_keys:
                while True:
                    keys = read_keys()
                    if not keys:
                        continue
                    with lock:
                        visible_count = state.visible_count()
                        page_size = max(shutil.get_terminal_size().lines - 5, 1)
                        for key in keys:
                            action, value = _key_action(key, state.filtering)
                            if action == "quit":
                                return
                            elif action == "sort":
                                selected_column = int(value) - 1
                                state.descending = (
                                    not state.descending
                                    if selected_column == state.sort_column
                                    else selected_column != 0
                                )
                                state.sort_column = selected_column
                                if selected_column in (4, 5):
                                    state.show_io = True
                                elif selected_column != 0:
                                    state.show_io = False
                                state.rows.sort(
                                    key=lambda row: _sort_value(row, state.sort_column), reverse=state.descending
                                )
                                state.cursor = 0
                            elif action == "up":
                                state.cursor = max(state.cursor - 1, 0)
                            elif action == "down":
                                state.cursor = min(state.cursor + 1, max(visible_count - 1, 0))
                            elif action == "page_up":
                                state.cursor = max(state.cursor - page_size, 0)
                            elif action == "page_down":
                                state.cursor = min(state.cursor + page_size, max(visible_count - 1, 0))
                            elif action == "start_filter":
                                state.filtering = True
                            elif action == "toggle_io":
                                state.show_io = not state.show_io
                            elif action == "core_columns":
                                state.show_io = False
                            elif action == "io_columns":
                                state.show_io = True
                            elif action == "clear_filter":
                                state.query, state.filtering, state.cursor = "", False, 0
                            elif action == "backspace":
                                state.query, state.cursor = state.query[:-1], 0
                            elif action == "finish_filter":
                                state.filtering = False
                            elif action == "append_filter":
                                state.query, state.cursor = state.query + value, 0
                        render(refresh=True)
        except KeyboardInterrupt:
            stop.set()
        finally:
            stop.set()
