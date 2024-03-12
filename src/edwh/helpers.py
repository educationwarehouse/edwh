"""
This file contains re-usable helpers.
"""
import abc
import datetime
import functools
import sys
import typing
from typing import Optional

import click
import diceware
from invoke import Context


def confirm(prompt: str, default: bool = False) -> bool:
    """
    Prompt a user to confirm a (dangerous) action.
    By default, entering nothing (only enter) will result in False, unless 'default' is set to True.
    """
    allowed = {"y", "1"}
    if default:
        allowed.add(" ")

    answer = input(prompt).lower().strip()
    answer += " "

    return answer[0] in allowed


def executes_correctly(c: Context, argument: str) -> bool:
    """returns True if the execution was without error level"""
    return c.run(argument, warn=True, hide=True).ok


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
def dump_set_as_list(data: set[T]) -> list[T]:
    """
    Sets are converted to lists.
    """


@typing.overload
def dump_set_as_list(data: T) -> T:
    """
    Other datatypes remain untouched.
    """


def dump_set_as_list(data: set[T] | T) -> list[T] | T:
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
    selected: set[T_Key] = (),
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
        options = list(options.keys())

    for item in selected:
        if item not in options:
            # invalid
            continue

        idx = options.index(item)
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
    selected: T_Key = None,
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
    selected_index = None
    current_index = 0

    if isinstance(options, list):
        labels = options
    else:
        labels = list(options.values())
        options = list(options.keys())

    if selected in options:
        selected_index = current_index = options.index(selected)

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
