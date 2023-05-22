"""
This file contains re-usable helpers.
"""
import abc
import datetime
import sys

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


class Logger(abc.ABC):
    def log(self, *a):
        raise NotImplementedError("This is an abstract method")


class VerboseLogger(Logger):
    def __init__(self):
        self._then = self._now()

    def _now(self):
        return datetime.datetime.utcnow()

    def log(self, *a):
        delta = self._now() - self._then
        print(f"[{delta}]", *a, file=sys.stderr)


class NoopLogger(Logger):
    def log(self, *a):
        pass
