"""
This file contains re-usable helpers.
"""
import json
import os
import pathlib
import re
import sys
import typing
from dataclasses import dataclass, field
from pathlib import Path

import diceware
import invoke
import tabulate
import tomlkit  # can be replaced with tomllib when 3.10 is deprecated
import yaml
from invoke import task, Context

from termcolor import colored


def confirm(prompt: str, default=False) -> bool:
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
