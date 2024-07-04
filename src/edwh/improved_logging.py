import datetime as dt
import hashlib
import itertools
import json
import re
import sys
import typing
from datetime import datetime
from typing import Optional

import anyio

""" --- translated from colors.go in docker compose """


def ansi_color_code(code, format_opts=[]):
    res = "\033["
    for c in format_opts:
        res += f"{c};"
    return f"{res}{code}m"


ColorFn = typing.Callable[[str], str]


def make_color_func(code) -> ColorFn:
    def color_func(s):
        return f"{ansi_color_code(code)}{s}{ansi_color_code('0')}"

    return color_func


def build_rainbow():
    names = [
        "grey",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
    ]

    colors = {}
    for i, name in enumerate(names):
        colors[name] = make_color_func(str(30 + i))
        colors[f"intense_{name}"] = make_color_func(f"{30 + i};1")

    rainbow = [
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
    ]

    return rainbow


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
):
    # py4web-1  | [X] loaded _dashboard
    data = json.loads(line)
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
        if verbose:
            # full:
            timestamp = data["time"].ljust(30, " ")  # iso is up to 30 chars wide
        else:
            # default:
            timestamp = data["time"].split(".")[0]

        prefix = color(f"{human_name} |") + f" {timestamp} |"
    else:
        prefix = color(f"{human_name} |")

    print(prefix, log, end="")


def dc_log_name(short: str, long: str) -> str:
    """
    Combines the short dc container name (e.g. logger) with the long docker one (/dummy-docker-compose-logger-1)
        to create a name similar to what `docker compose logs` shows: 'logger-1' (-> getContainerNameWithoutProject)
    """
    container_idx = long.split("-")[-1]
    return f"{short}-{container_idx}".strip()


TD_RE = re.compile(r"(\d+)\s*(hour|minute|second|day)s?\s*(ago)?")


def _parse_timedelta(since: str) -> Optional[dt.timedelta]:
    if since == "now":
        # 0.1s because otherwise the timedelta is falsey
        return dt.timedelta(seconds=0.1)

    if not (since and (match := TD_RE.match(since))):
        return None

    number = int(match.group(1))
    unit = match.group(2)

    match unit:
        case "day":
            return dt.timedelta(days=number)
        case "hour":
            return dt.timedelta(hours=number)
        case "minute":
            return dt.timedelta(minutes=number)
        case "second":
            return dt.timedelta(seconds=number)
        case _:
            print(f"Warn: unrecognized unit {unit}.", file=sys.stderr)
            return None


def utcnow():
    """
    Replacement of datetime.utcnow.
    """
    return datetime.now(dt.UTC)


def parse_timedelta(since: str, utc: bool = True) -> str:
    # turns human-readable 'since' into a iso datetime string.

    if delta := _parse_timedelta(since):
        now = utcnow() if utc else datetime.now()
        print("since", (now - delta).isoformat())
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
        _, *rest, flags = raw.split("/")
        flags = set(flags.lower())
        pattern = "/".join(rest)
    else:
        # normal search mode, no flags
        flags = set()
        pattern = raw

    flags_bin = re.NOFLAG

    for flag in flags:
        flags_bin |= POSSIBLE_FLAGS.get(flag) or re.NOFLAG

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


async def tail(config: TailConfig):
    async with await anyio.open_file(config["filename"]) as f:
        while True:
            if contents := await f.readline():
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
