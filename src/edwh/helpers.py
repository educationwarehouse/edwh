"""
This file contains re-usable helpers.
"""
import abc
import datetime
import sys
import typing

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


def arg_was_passed(flag: str | tuple[str, ...]) -> typing.Optional[int]:
    """
    Returns the index of the flag in sys.argv if passed, else None
    """
    flag = flag if isinstance(flag, tuple) else (flag,)
    flag = tuple(_add_dash(f) for f in flag)
    # flag and sys.argv should now both be in the same format: -x and --flag
    return next((i for i, item in enumerate(sys.argv) if item in flag), None)


def kwargs_to_options(data: dict = None, **kw) -> str:
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


def interactive_selected_checkbox_values(
    options: list[str],
    prompt: str = "Select options (use arrow keys, spacebar, or digit keys, press 'Enter' to finish):",
) -> list[str]:
    """
    This function provides an interactive checkbox selection in the console.

    The user can navigate through the options using the arrow keys,
    select/deselect options using the spacebar or digit keys, and finish the selection by pressing 'Enter'.

    Args:
        options (list[str]): A list of options to be displayed as checkboxes.
        prompt (str, optional): A string that is displayed as a prompt for the user.

    Returns:
        list[str]: A list of selected option values.

    """
    checked_indices = dict()  # instead of set to keep ordering
    current_index = 0

    def print_checkbox(label: str, checked: bool, current: bool, number: int) -> None:
        checkbox = "[x]" if checked else "[ ]"
        indicator = ">" if current else " "
        click.echo(f"{indicator}{number}. {checkbox} {label}")

    while True:
        click.clear()
        click.echo(prompt)

        for i, option in enumerate(options, start=1):
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
