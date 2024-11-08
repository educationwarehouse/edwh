"""
This file contains re-usable helpers.
"""

import abc
import datetime as dt
import functools
import io
import os
import sys
import typing
from pathlib import Path
from typing import Optional

import click
import diceware
import yaml
from fabric.connection import Connection
from invoke.context import Context
from more_itertools import flatten as _flatten

from .constants import DOCKER_COMPOSE

AnyDict: typing.TypeAlias = dict[str, typing.Any]


def confirm(prompt: str, default: bool = False, allowed: Optional[set[str]] = None, strict: bool = False) -> bool:
    """
    Prompt a user to confirm a (dangerous) action.
    By default, entering nothing (only enter) will result in False, unless 'default' is set to True.
    """
    allowed = allowed or {"y", "1"}
    if default:
        allowed.add(" ")

    answer = input(prompt).lower().strip()
    answer += " "

    confirmed = answer.strip() in allowed or answer[0] in allowed

    if strict and not confirmed:
        raise RuntimeError(f"Stopping now because '{answer.strip()}' did not match {allowed}.")

    return confirmed


def executes_correctly(c: Context, argument: str) -> bool:
    """returns True if the execution was without error level"""
    ran = c.run(argument, warn=True, hide=True)
    return bool(ran and ran.ok)


def execution_fails(c: Context, argument: str) -> bool:
    """Returns true if the execution fails based on error level"""
    return not executes_correctly(c, argument)


def generate_password(silent: bool = True, dice: int = 6) -> str:
    """Generate a diceware password using --dice 6."""
    options = diceware.handle_options(args=[])
    options.num = dice
    password: str = diceware.get_passphrase(options)
    if not silent:
        print("Password:", password)
    return password


# T = typing.TypeVar("T", str, bool)


def _add_dash(flag: str) -> str:
    if flag.startswith("-"):
        # don't change
        return flag
    if len(flag) == 1:
        # one letter, -x
        return f"-{flag}"
    else:
        # multiple letters --flag
        return f"--{flag}"


def arg_was_passed(flag: str | tuple[str, ...]) -> Optional[int]:
    """
    Returns the index of the flag in sys.argv if passed, else None
    """
    flag = flag if isinstance(flag, tuple) else (flag,)
    flag = tuple(_add_dash(f) for f in flag)
    # flag and sys.argv should now both be in the same format: -x and --flag
    return next((i for i, item in enumerate(sys.argv) if item in flag), None)


def kwargs_to_options(data: Optional[AnyDict] = None, **kw: typing.Any) -> str:
    """
    Convert a dictionary of options to the cli variant
    e.g. {'a': 1, 'key': 2} -> -a 1 --key 2
    """
    if data:
        kw |= data

    options = []
    for key, value in kw.items():
        if value in (None, "", False):
            # skip falsey, but keep 0
            continue

        pref = ("-" if len(key) == 1 else "--") + key

        if isinstance(value, bool):
            options.append(f"{pref}")

        elif isinstance(value, list):
            options.extend(f"{pref} {subvalue}" for subvalue in value)
        else:
            options.append(f"{pref} {value}")

    return " " + " ".join(options)


class Logger(abc.ABC):
    def log(self, *a: typing.Any) -> None:
        raise NotImplementedError("This is an abstract method")


class VerboseLogger(Logger):
    def __init__(self) -> None:
        self._then = self._now()
        self._previous = self._now()

    @staticmethod
    def _now() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    def log(self, *a: typing.Any) -> None:
        now = self._now()
        delta_start = now - self._then
        delta_prev = now - self._previous
        print(f"[{delta_start}, +{delta_prev}]", *a, file=sys.stderr)
        self._previous = now


# usage:
# logger = VerboseLogger()
# log = logger.log
# ...
# log("some event")


class NoopLogger(Logger):
    def log(self, *_: typing.Any) -> None:
        return None


def noop(*_: typing.Any, **__: typing.Any) -> None:
    return None


T = typing.TypeVar("T")


@typing.overload
def dump_set_as_list(data: set[T]) -> list[T]:
    """
    Sets are converted to lists.
    """


@typing.overload
def dump_set_as_list(data: T) -> T:
    """
    Other datatypes remain untouched.
    """


def dump_set_as_list(data: set[T] | T) -> list[T] | T:  # type: ignore
    if isinstance(data, set):
        return list(data)
    else:
        return data


KEY_ENTER = "\r"
KEY_ARROWUP = "\033[A"
KEY_ARROWDOWN = "\033[B"

T_Key = typing.TypeVar("T_Key", bound=typing.Hashable)


def print_box(label: str, selected: bool, current: bool, number: int, fmt: str = "[%s]", filler: str = "x") -> None:
    box = fmt % (filler if selected else " ")
    indicator = ">" if current else " "
    click.echo(f"{indicator}{number}. {box} {label}")


def interactive_selected_checkbox_values(
    options: list[str] | dict[T_Key, str],
    prompt: str = "Select options (use arrow keys, spacebar, or digit keys, press 'Enter' to finish):",
    selected: typing.Collection[T_Key] = (),
    allow_empty: bool = False,
) -> list[str] | None:
    """
    This function provides an interactive checkbox selection in the console.

    The user can navigate through the options using the arrow keys,
    select/deselect options using the spacebar or digit keys, and finish the selection by pressing 'Enter'.

    Args:
        options: A list or dict (value: label) of options to be displayed as checkboxes.
        prompt (str, optional): A string that is displayed as a prompt for the user.
        allow_empty (bool, optional): If True, adds an extra option "(none)" to deselect all other options.
        selected: a set (/other iterable) of pre-selected options (set is preferred).

            T_Key means the values have to be the same type as the keys of options.
            Example:
                options = {1: "something", "two": "else"}
                selected = [2, "three"] # valid type (int and str are keys of options)
                selected = [1.5, "two"] # invalid type (none of the keys of options are a float)

    Returns:
        list[str]: A list of selected option values.

    Examples:
        interactive_selected_checkbox_values(["first", "second", "third"])

        interactive_selected_checkbox_values({100: "first", 211: "second", 355: "third"})

        interactive_selected_checkbox_values(["first", "second", "third"], selected=["third"])

        interactive_selected_checkbox_values({1: "first", 2: "second", 3: "third"}, selected=[3])
    """
    checked_indices = dict()  # instead of set to keep ordering
    current_index = 0

    if isinstance(options, list):
        labels = options
    else:
        labels = list(options.values())
        options = list(options.keys())  # type: ignore

    for item in selected:
        if item not in options:
            # invalid
            continue

        idx = options.index(item)  # type: ignore
        checked_indices[idx] = options[idx]

    if allow_empty:
        labels.append("(none)")

    print_checkbox = functools.partial(print_box, fmt="[%s]", filler="x")

    while True:
        click.clear()
        click.echo(prompt)

        for i, option in enumerate(labels, start=1):
            print_checkbox(option, i - 1 in checked_indices, i - 1 == current_index, i)

        key = click.getchar()

        if key == KEY_ENTER:
            break
        elif key == KEY_ARROWUP:  # Up arrow
            current_index = (current_index - 1) % len(labels)
        elif key == KEY_ARROWDOWN:  # Down arrow
            current_index = (current_index + 1) % len(labels)
        elif key.isdigit() and 1 <= int(key) <= len(labels):
            current_index = int(key) - 1
        elif key == " ":
            if allow_empty and current_index == len(labels) - 1:
                checked_indices.clear()
                checked_indices[len(labels) - 1] = "(none)"
            else:
                if len(checked_indices) == 1 and set(checked_indices.values()) == {"(none)"}:
                    checked_indices.clear()
                if current_index in checked_indices:
                    del checked_indices[current_index]
                else:
                    checked_indices[current_index] = options[current_index]

    if allow_empty and len(checked_indices) == 1 and set(checked_indices.values()) == {"(none)"}:
        # None instead of empty list since otherwise it would just ask again
        return None

    return list(checked_indices.values())


def interactive_selected_radio_value(
    options: list[str] | dict[T_Key, str],
    prompt: str = "Select an option (use arrow keys, spacebar, or digit keys, press 'Enter' to finish):",
    selected: Optional[T_Key] = None,
    allow_empty: bool = False,
) -> str | None:
    """
    This function provides an interactive radio box selection in the console.

    The user can navigate through the options using the arrow keys,
    select an option using the spacebar or digit keys, and finish the selection by pressing 'Enter'.

    Args:
        options: A list or dict (value: label) of options to be displayed as radio boxes.
        prompt (str, optional): A string that is displayed as a prompt for the user.
        allow_empty (bool, optional): If True, adds an extra option "(none)" to allow deselecting all options.
        selected: a pre-selected option.
            T_Key means the value has to be the same type as the keys of options.
            Example:
                options = {1: "something", "two": "else"}
                selected = 2 # valid type (int is a key of options)
                selected = 1.5 # invalid type (none of the keys of options are a float)

    Returns:
        str: The selected option value, or an empty string if (none) is selected.

    Examples:
        interactive_selected_radio_value(["first", "second", "third"])

        interactive_selected_radio_value({100: "first", 211: "second", 355: "third"})

        interactive_selected_radio_value(["first", "second", "third"], selected="third")

        interactive_selected_radio_value({1: "first", 2: "second", 3: "third"}, selected=3)
    """
    selected_index: Optional[int] = None
    current_index = 0

    if isinstance(options, list):
        labels = options
    else:
        labels = list(options.values())
        options = list(options.keys())  # type: ignore

    if selected in options:
        selected_index = current_index = options.index(selected)  # type: ignore

    if allow_empty:
        labels.append("(none)")

    print_radio_box = functools.partial(print_box, fmt="(%s)", filler="o")

    while True:
        click.clear()
        click.echo(prompt)

        for i, option in enumerate(labels, start=1):
            print_radio_box(option, i - 1 == selected_index, i - 1 == current_index, i)

        key = click.getchar()

        if key == KEY_ENTER:
            if selected_index is None:
                # no you may not leave.
                continue
            else:
                # done!
                break

        elif key == KEY_ARROWUP:  # Up arrow
            current_index = (current_index - 1) % len(labels)
        elif key == KEY_ARROWDOWN:  # Down arrow
            current_index = (current_index + 1) % len(labels)
        elif key.isdigit() and 1 <= int(key) <= len(labels):
            selected_index = int(key) - 1
        elif key == " ":
            selected_index = current_index

    if allow_empty and selected_index == len(labels) - 1:
        return None

    return options[selected_index]


def yaml_loads(text: str) -> AnyDict:
    dct = yaml.load(
        text,
        Loader=yaml.SafeLoader,
    )
    return typing.cast(AnyDict, dct)


def dc_config(ctx: Context) -> AnyDict:
    if ran := ctx.run(f"{DOCKER_COMPOSE} config", warn=True, echo=False, hide=True):
        return (
            yaml_loads(
                ran.stdout.strip(),
            )
            or {}
        )
    else:
        return {}


def print_aligned(plugin_commands: list[str]) -> None:
    """
    Prints a list of plugin commands in an aligned format.

    This function takes a list of plugin commands, each of which is a string containing two parts separated by a tab.
    It splits each command into two parts, calculates the maximum length of the first part across all commands,
    and then prints each command with the first part left-justified to the maximum length. This ensures that the
    second parts of all commands are aligned in the output.

    Args:
        plugin_commands (list[str]): A list of plugin commands. Each command is a string containing two parts
            separated by a tab.

    Example:
        print_aligned(["command1\tdescription1", "command_with_long_name\tdescription2"])
        # Output:
        #     command1                 description1
        #     command_with_long_name   description2
    """
    splitted = [_.split("\t") for _ in plugin_commands]
    max_l = max([len(_[0]) for _ in splitted])

    for before, after in splitted:
        print("\t", before.ljust(max_l, " "), "\t\t", after)


def flatten(something: typing.Iterable[typing.Iterable[T]]) -> list[T]:
    """
    Like itertools.flatten but eager
    """
    return list(_flatten(something))


def shorten(text: str, max_chars: int) -> str:
    """
    textwrap looks at words and stuff, not relevant for commands!
    """
    if len(text) <= max_chars:
        return text
    else:
        return f"{text[:max_chars]}..."


def _fabric_resolve_home(path: str, user: str) -> str:
    if not path.startswith("~"):
        return path

    return path.replace("~", f"/home/{user}", 1)


def _write_bytes_remote(c: Connection, path: str, contents: bytes, parents: bool = False) -> None:
    f = io.BytesIO(contents)

    if parents:
        # ensure path to file exists
        parent_path = os.path.dirname(path)
        c.run(f"mkdir -p {parent_path}")

    c.put(f, path)


def _write_bytes_local(_: Context, path: str, contents: bytes, parents: bool = False) -> None:
    p = Path(path)
    if parents:
        p.parent.mkdir(parents=True, exist_ok=True)

    p.write_bytes(contents)


class WriteBytesFn(typing.Protocol):
    def __call__(self, c: Connection | Context, path: str, contents: bytes, parents: bool = False) -> None: ...


def fabric_write(c: Connection | Context, path: str, contents: str | bytes, parents: bool = False) -> None:
    """
    Write some contents to a remote file.
    ~ will be resolved to the remote user's home
    """
    path = _fabric_resolve_home(path, c.user)

    fn = typing.cast(WriteBytesFn, _write_bytes_remote if isinstance(c, Connection) else _write_bytes_local)

    return fn(c, path, contents if isinstance(contents, bytes) else contents.encode(), parents=parents)


def _read_bytes_remote(c: Connection, path: str) -> bytes:
    buf = io.BytesIO()
    c.get(path, buf)

    buf.seek(0)
    return buf.read()


def _read_bytes_local(_: Context, path: str) -> bytes:
    return Path(path).read_bytes()


ReadBytesFn: typing.TypeAlias = typing.Callable[[Connection | Context, str], bytes]


def fabric_read_bytes(c: Connection | Context, path: str, throw: bool = True) -> bytes:
    """
    Write some bytes from a remote file.
    ~ will be resolved to the remote user's home
    """
    path = _fabric_resolve_home(path, c.user)

    fn: ReadBytesFn = _read_bytes_remote if isinstance(c, Connection) else _read_bytes_local

    try:
        return fn(c, path)
    except FileNotFoundError:
        if throw:
            raise
        else:
            return b""


def fabric_read(c: Connection | Context, path: str, throw: bool = True) -> str:
    """
    Write some text from a remote file.
    ~ will be resolved to the remote user's home
    """
    b = fabric_read_bytes(c, path, throw=throw)
    return b.decode()


def _add_alias(sometask: typing.Any, alias: str):
    if alias not in sometask.aliases:
        sometask.aliases = (*sometask.aliases, alias)


def add_alias(sometask: typing.Any, aliases: str | typing.Iterable[str]):
    """
    Add an extra alias to an existing task (usually in ~/.config/edwh/tasks.py).

    Example:
        >>> edwh.add_alias(edwh.tasks.migrate, "migarte")
        >>> edwh.add_alias(edwh.tasks.migrate, ["migarte"])
        >>> edwh.add_alias(edwh.tasks.migrate, ("migarte",))
    """
    if isinstance(aliases, str):
        aliases = [aliases]

    for alias in aliases:
        _add_alias(sometask, alias)
