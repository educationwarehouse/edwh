import datetime as dt
import hashlib
import json
import re
import sys
import typing
from datetime import datetime
from typing import Optional

import anyio


def string_to_ansi_color_code(input_string):
    # Generate a SHA1 hash of the input string
    hash_object = hashlib.sha1(input_string.encode())
    hex_dig = hash_object.hexdigest()

    # Take the first 6 characters of the hash as the color code
    color_code = hex_dig[:6]

    # Convert the color code to an ANSI escape sequence
    ansi_color_code = f"\033[38;2;{int(color_code[:2], 16)};{int(color_code[2:4], 16)};{int(color_code[4:], 16)}m"

    return ansi_color_code


def in_color(input_string: str, hash_string: Optional[str] = None):
    # Get the ANSI color code for the input string
    color_code = string_to_ansi_color_code(hash_string or input_string)

    # the input string in color and then reset the color
    return f"{color_code}{input_string}\033[0m"


FilterFn: typing.TypeAlias = Optional[typing.Callable[[str], bool]]


async def parse_docker_log_line(
    line: str,
    human_name: str,
    container_id: str,
    stream: Optional[str] = None,
    since: Optional[str] = None,
    re_filter: FilterFn = None,
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

    print(in_color(human_name, container_id), "|", log, end="")


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
                )
