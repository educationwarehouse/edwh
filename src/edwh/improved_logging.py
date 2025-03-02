import asyncio
import datetime as dt
import itertools
import re
import sys
import typing
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import docker
import docker.errors
from termcolor import cprint

from .constants import AnyDict


def ansi_color_code(code: str, format_opts: typing.Collection[str] = ()) -> str:
    res = "\033["
    for c in format_opts:
        res += f"{c};"
    return f"{res}{code}m"


ColorFn = typing.Callable[[str], str]


def make_color_func(code: str) -> ColorFn:
    return lambda s: f"{ansi_color_code(code)}{s}{ansi_color_code('0')}"


def build_rainbow() -> tuple[ColorFn, ...]:
    """--- translated from colors.go in docker compose"""

    names = (
        "grey",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
    )

    colors = {}
    for i, name in enumerate(names):
        colors[name] = make_color_func(str(30 + i))
        colors[f"intense_{name}"] = make_color_func(f"{30 + i};1")

    return (
        colors["cyan"],
        colors["yellow"],
        colors["green"],
        colors["magenta"],
        colors["blue"],
        colors["intense_cyan"],
        colors["intense_yellow"],
        colors["intense_green"],
        colors["intense_magenta"],
        colors["intense_blue"],
    )


def rainbow() -> typing.Generator[ColorFn, None, None]:
    """
    rainbow = []colorFunc{
                colors["cyan"],
                colors["yellow"],
                colors["green"],
                colors["magenta"],
                colors["blue"],
                colors["intense_cyan"],
                colors["intense_yellow"],
                colors["intense_green"],
                colors["intense_magenta"],
                colors["intense_blue"],
        }

    Yield colors from the docker compose rainbow map in a cyclic way.
    """
    yield from itertools.cycle(build_rainbow())


""" -- end of colors.go """

FilterFn: typing.TypeAlias = Optional[typing.Callable[[str], bool]]

TD_RE = re.compile(r"(\d+)\s*(h(our)?|m(inute)?|s(econd)?|d(ay)?)s?\s*(ago)?", re.IGNORECASE)


def _parse_timedelta(since: str) -> Optional[dt.timedelta]:
    if since == "now":
        # 0.1s because otherwise the timedelta is falsey
        return dt.timedelta(seconds=0.1)

    if not (since and (match := TD_RE.match(since))):
        return None

    number = int(match.group(1))
    unit = match.group(2)

    match unit.lower():
        case "day" | "d":
            return dt.timedelta(days=number)
        case "hour" | "h":
            return dt.timedelta(hours=number)
        case "minute" | "m":
            return dt.timedelta(minutes=number)
        case "second" | "s":
            return dt.timedelta(seconds=number)
        case _:
            print(f"Warn: unrecognized unit {unit}.", file=sys.stderr)
            return None


def utcnow() -> dt.datetime:
    """
    Replacement of datetime.utcnow.

    When 3.13 is released, 3.10 can be dropped and this check can also be removed.
    """
    if sys.version_info < (3, 11):
        # deprecated since 3.12
        return datetime.utcnow()
    else:
        # dt.UTC doesn't exist yet in 3.10
        return datetime.now(dt.UTC)


def parse_timedelta(since: str, utc: bool = True) -> str:
    # turns human-readable 'since' into a iso datetime string.

    if delta := _parse_timedelta(since):
        now = utcnow() if utc else datetime.now()
        return (now - delta).isoformat()

    return since


def parse_timedelta_as_dt(since: str, utc: bool = True) -> dt.datetime:
    # turns human-readable 'since' into a datetime.
    if delta := _parse_timedelta(since):
        now = utcnow() if utc else datetime.now()
        return now - delta

    return dt.datetime.fromisoformat(since)


POSSIBLE_FLAGS = {
    # https://docs.python.org/3/library/re.html
    "a": re.ASCII,
    "d": re.DEBUG,
    "i": re.IGNORECASE,
    "l": re.LOCALE,
    "m": None,  # re.MULTILINE but the logger works line-by-line so this isn't really possible
    "s": re.DOTALL,
    "u": re.UNICODE,
    "x": re.VERBOSE,
    # custom: 'v' to invert
}


def parse_regex(raw: str) -> FilterFn:
    """
    Turn `/pattern/flags` into a Regex object.

    Uses the grep style flags (i for case insensitive, v for invert)
    """

    # zero slashes: just a pattern, no flags.
    # one slash: search term with / in it
    # two slashes (+ starts with /): regex with flags
    # more slashes: flags AND / in filter itself

    if raw.startswith("/") and raw.count("/") > 1:
        # flag-mode
        _, *rest, flags_str = raw.split("/")
        flags = set(flags_str.lower())
        pattern = "/".join(rest)
    else:
        # normal search mode, no flags
        flags = set()
        pattern = raw

    flags_bin = 0  # re.NOFLAG doesn't exist in 3.10 yet

    for flag in flags:
        flags_bin |= POSSIBLE_FLAGS.get(flag) or 0  # re.NOFLAG

    re_compiled = re.compile(pattern, flags_bin)

    if "v" in flags:
        # v for inverse like `grep -v`
        return lambda text: not re_compiled.search(text)
    else:
        return lambda text: bool(re_compiled.search(text))


@dataclass
class LogEntry:
    """Log entry object for priority queue sorting"""

    timestamp: dt.datetime
    message: str
    container_id: str
    human_name: str
    color: ColorFn

    def __lt__(self, other):
        return self.timestamp < other.timestamp  # Ensures priority queue sorting by timestamp


async def process_logs(
    queue: asyncio.PriorityQueue,
    show_ts: bool = True,
    verbose: bool = False,
):
    """Print logs in order of timestamp."""
    print_args = " ".join(sys.argv[1:])
    while True:
        await asyncio.sleep(0.0001)  # avoid tight loop
        entry: LogEntry = await queue.get()
        timestamp = entry.timestamp.isoformat()

        if not (log := entry.message):
            continue

        if verbose:
            container_label = entry.color(f"{entry.human_name} [{entry.container_id}] |")
        else:
            container_label = entry.color(f"{entry.human_name} |")

        if show_ts:
            # iso is up to 30 chars wide
            timestamp = timestamp.ljust(30, " ") if verbose else timestamp.split(".")[0]

            prefix = container_label + f" {timestamp} |"
        else:
            prefix = container_label

        print(prefix, log, end="")
        cprint(f"$ edwh {print_args}", color="white", end="\r")


async def fetch_logs(
    container_id: str,
    human_name: str,
    color: ColorFn,
    queue: asyncio.PriorityQueue,
    since: dt.datetime | None = None,
    stdout: bool = True,
    stderr: bool = True,
    re_filter: FilterFn = None,
):
    """Fetch logs from a Docker container and push them to a priority queue."""
    client = docker.from_env()
    container = client.containers.get(container_id)

    since = since or dt.datetime.fromtimestamp(0, tz=dt.timezone.utc)

    while True:
        await asyncio.sleep(0.001)  # Avoid tight loop
        lines = container.logs(
            stream=True, follow=False, stdout=stdout, stderr=stderr, timestamps=True, since=since.timestamp() + 0.001
        )

        try:
            for row in lines:
                if not row:
                    continue

                ts_str, log = row.decode().split(" ", 1)

                if re_filter and not re_filter(log):
                    continue

                new_since = dt.datetime.fromisoformat(ts_str)

                if new_since > since:
                    since = new_since

                await queue.put(LogEntry(new_since, log, container_id, human_name, color))

        except StopIteration:
            await asyncio.sleep(0.1)


async def logs_improved_async(
    services: list[str],
    containers: dict[str, AnyDict],
    since: Optional[str] = None,
    new: bool = False,
    re_filter: Optional[str] = None,
    stream: Optional[str] = None,
    timestamps: bool = True,
    verbose: bool = False,
) -> None:
    if new:
        since = "now"

    if since:
        since = parse_timedelta_as_dt(since)

    if stream is None:
        stdout = True
        stderr = True
    elif stream == "stderr":
        stdout = False
        stderr = True
    elif stream == "stdout":
        stdout = True
        stderr = False
    else:
        raise ValueError("Stream should be stdout or stderr")

    re_filter_fn = parse_regex(re_filter) if re_filter else None

    if not containers:
        cprint(f"No running containers found for services {services}", color="red")
        exit(1)
    elif len(containers) != len(services):
        cprint("Amount of requested services does not match the amount of running containers!", color="yellow")

    # for adjusting the | location
    longest_name = max([len(_["Service"]) for _ in containers.values()])

    print("---", file=sys.stderr)
    queue = asyncio.PriorityQueue()

    tasks = []
    colors = rainbow()
    for container_id, container_info in containers.items():
        container_name = (
            container_info["Name"].removeprefix(container_info["Project"] + "-").ljust(longest_name + 3, " ")
        )

        # Start fetching logs
        tasks.append(
            asyncio.create_task(
                fetch_logs(
                    container_id,
                    human_name=container_name,
                    queue=queue,
                    color=next(colors),
                    since=since,
                    stdout=stdout,
                    stderr=stderr,
                    re_filter=re_filter_fn,
                )
            )
        )

    # Start log processing task
    processor_task = asyncio.create_task(process_logs(queue, show_ts=timestamps, verbose=verbose))

    try:
        await asyncio.gather(*tasks, processor_task)  # Wait for all tasks to complete
    except docker.errors.APIError:
        return
