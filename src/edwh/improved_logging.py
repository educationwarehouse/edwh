import datetime as dt
import itertools
import json
import re
import sys
import typing
from datetime import datetime
from pathlib import Path
from typing import Optional

import anyio
from termcolor import cprint

""" --- translated from colors.go in docker compose """


def ansi_color_code(code: str, format_opts: typing.Collection[str] = ()) -> str:
    res = "\033["
    for c in format_opts:
        res += f"{c};"
    return f"{res}{code}m"


ColorFn = typing.Callable[[str], str]


def make_color_func(code: str) -> ColorFn:
    return lambda s: f"{ansi_color_code(code)}{s}{ansi_color_code('0')}"


def build_rainbow() -> tuple[ColorFn, ...]:
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


def rainbow() -> typing.Generator[str, None, None]:
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


async def parse_docker_log_line(
    line: str,
    human_name: str,
    container_id: str,
    color: ColorFn,
    stream: Optional[str] = None,
    since: Optional[str] = None,
    re_filter: FilterFn = None,
    show_ts: bool = True,  # full, default, no
    verbose: bool = False,
) -> None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        # don't crash, just ignore
        return

    # data containers log, stream (stdout/stderr) and time.

    if stream and data["stream"] != stream:
        return

    if since and data["time"] < since:
        return

    if not (log := data.get("log")):
        return

    if re_filter and not re_filter(log):
        return

    if show_ts:
        # iso is up to 30 chars wide
        timestamp = data["time"].ljust(30, " ") if verbose else data["time"].split(".")[0]

        prefix = color(f"{human_name} |") + f" {timestamp} |"
    else:
        prefix = color(f"{human_name} |")

    print(prefix, log, end="")


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


class TailConfig(typing.TypedDict):
    filename: str
    human_name: str
    container_id: str
    stream: Optional[str]
    since: Optional[str]
    re_filter: Optional[FilterFn]
    color: ColorFn
    timestamps: bool
    verbose: bool
    state: str


async def tail(config: TailConfig) -> None:
    print_args = " ".join(sys.argv[1:])
    fname = config["filename"]
    fpath = Path(fname)

    if not fpath.exists():
        cprint(f"Expected log file but found nothing. Container {config['human_name']} state: {config['state']}")
        return

    async with await anyio.open_file(fname) as f:
        while True:
            # if the file doesn't exist, the container was removed (dc down)
            exited = config["state"] == "exited" or not fpath.exists()

            if contents := await f.readline():
                print(" " * 20, end="\r")
                await parse_docker_log_line(
                    contents,
                    config["human_name"],
                    config["container_id"],
                    stream=config.get("stream"),
                    since=config.get("since"),
                    re_filter=config.get("re_filter"),
                    color=config["color"],
                    show_ts=config["timestamps"],
                    verbose=config["verbose"],
                )
                cprint(f"$ edwh {print_args}", color="white", end="\r")
            elif exited:
                # if state = 'exited' and last line was reached -> stop
                # note: this only happens when the container was already shut down when 'logs' started,
                # exited is NOT updated live. This was done on purpose, so restarting containers keep being logged.
                # but if the container was already shut down, it's probably something like migrate,
                # which will not restart automatically, so you probably don't want to wait forever.
                return
            else:
                # Add a small sleep to reduce CPU load (if no data right now)
                await anyio.sleep(0.1)
