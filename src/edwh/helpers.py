"""
This file contains re-usable helpers.
"""

import abc
import datetime
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
from fabric import Connection
from invoke import Context
from more_itertools import flatten as _flatten

from .constants import DOCKER_COMPOSE


def confirm(prompt: str, default: bool = False, allowed: Optional[set[str]] = None, strict=False) -> bool:
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


def generate_password(silent=True):
    """Generate a diceware password using --dice 6."""
    password = diceware.get_passphrase()
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


def kwargs_to_options(data: Optional[dict] = None, **kw) -> str:
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
    def log(self, *a):
        raise NotImplementedError("This is an abstract method")


class VerboseLogger(Logger):
    def __init__(self):
        self._then = self._now()
        self._previous = self._now()

    @staticmethod
    def _now():
        return datetime.datetime.now(datetime.timezone.utc)

    def log(self, *a):
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
    def log(self, *a) -> None:
        pass


def noop(*_, **__) -> None:
    return None


T = typing.TypeVar("T")


@typing.overload
def dump_set_as_list(data: set[T]) -> list[T]:  # type: ignore
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
) -> list[str]:
    """
    This function provides an interactive checkbox selection in the console.

    The user can navigate through the options using the arrow keys,
    select/deselect options using the spacebar or digit keys, and finish the selection by pressing 'Enter'.

    Args:
        options: A list or dict (value: label) of options to be displayed as checkboxes.
        prompt (str, optional): A string that is displayed as a prompt for the user.
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
            current_index = (current_index - 1) % len(options)
        elif key == KEY_ARROWDOWN:  # Down arrow
            current_index = (current_index + 1) % len(options)
        elif key.isdigit() and 1 <= int(key) <= len(options):
            current_index = int(key) - 1
            if current_index in checked_indices:
                del checked_indices[current_index]
            else:
                checked_indices[current_index] = options[current_index]
        elif key == " ":
            if current_index in checked_indices:
                del checked_indices[current_index]
            else:
                checked_indices[current_index] = options[current_index]

    return list(checked_indices.values())


def interactive_selected_radio_value(
    options: list[str] | dict[T_Key, str],
    prompt: str = "Select an option (use arrow keys, spacebar, or digit keys, press 'Enter' to finish):",
    selected: Optional[T_Key] = None,
) -> str:
    """
    This function provides an interactive radio box selection in the console.

    The user can navigate through the options using the arrow keys,
    select an option using the spacebar or digit keys, and finish the selection by pressing 'Enter'.

    Args:
        options: A list or dict (value: label) of options to be displayed as radio boxes.
        prompt (str, optional): A string that is displayed as a prompt for the user.
        selected: a pre-selected option.
            T_Key means the value has to be the same type as the keys of options.
            Example:
                options = {1: "something", "two": "else"}
                selected = 2 # valid type (int is a key of options)
                selected = 1.5 # invalid type (none of the keys of options are a float)

    Returns:
        str: The selected option value.

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
            current_index = (current_index - 1) % len(options)
        elif key == KEY_ARROWDOWN:  # Down arrow
            current_index = (current_index + 1) % len(options)
        elif key.isdigit() and 1 <= int(key) <= len(options):
            selected_index = int(key) - 1
        elif key == " ":
            selected_index = current_index

    return options[selected_index]


def yaml_loads(text: str) -> dict[str, typing.Any]:
    return yaml.load(
        text,
        Loader=yaml.SafeLoader,
    )


def dc_config(ctx: Context) -> dict[str, typing.Any]:
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


def fabric_write(c: Connection | Context, path: str, contents: str | bytes, parents: bool = False) -> None:
    """
    Write some contents to a remote file.
    ~ will be resolved to the remote user's home
    """
    path = _fabric_resolve_home(path, c.user)
    contents = contents if isinstance(contents, bytes) else contents.encode()

    if not isinstance(c, Connection):
        # local
        Path(path).write_bytes(contents)
        return

    f = io.BytesIO(contents)

    if parents:
        # ensure path to file exists
        parent_path = os.path.dirname(path)
        c.run(f"mkdir -p {parent_path}")

    c.put(f, path)


def fabric_read_bytes(c: Connection | Context, path: str, throw: bool = True) -> bytes:
    """
    Write some bytes from a remote file.
    ~ will be resolved to the remote user's home
    """
    path = _fabric_resolve_home(path, c.user)

    if not isinstance(c, Connection):
        # local
        return Path(path).read_bytes()

    buf = io.BytesIO()
    try:
        c.get(path, buf)
    except FileNotFoundError:
        if throw:
            raise
        else:
            return b""

    buf.seek(0)
    return buf.read()


def fabric_read(c: Connection | Context, path: str, throw: bool = True) -> str:
    """
    Write some text from a remote file.
    ~ will be resolved to the remote user's home
    """
    b = fabric_read_bytes(c, path, throw=throw)
    return b.decode()
