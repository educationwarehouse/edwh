"""
This file contains re-usable helpers.
"""
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
