"""
This file exposes some functions so this tool can be used as a library.
"""

# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT

import warnings

from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)  # noqa

from . import tasks
from .constants import DOCKER_COMPOSE
from .helpers import (
    KEY_ARROWDOWN,
    KEY_ARROWUP,
    KEY_ENTER,
    AnyDict,
    Logger,
    NoopLogger,
    VerboseLogger,
    add_alias,
    arg_was_passed,
    confirm,
    dc_config,
    dump_set_as_list,
    executes_correctly,
    execution_fails,
    fabric_read,
    fabric_read_bytes,
    fabric_write,
    flatten,
    generate_password,
    interactive_selected_checkbox_values,
    interactive_selected_radio_value,
    kwargs_to_options,
    noop,
    print_aligned,
    print_box,
    shorten,
    yaml_loads,
)
from .improved_invoke import ImprovedTask, improved_task
from .tasks import (
    TomlConfig,
    check_env,
    get_env_value,
    get_task,
    read_dotenv,
    set_env_value,
    task_for_namespace,
)

Task = ImprovedTask
task = improved_task

__all__ = [
    "DOCKER_COMPOSE",
    "tasks",
    "add_alias",
    "AnyDict",
    "Task",
    "ImprovedTask",
    "task",
    "improved_task",
    "TomlConfig",
    "check_env",
    "get_env_value",
    "get_task",
    "read_dotenv",
    "set_env_value",
    "task_for_namespace",
    "confirm",
    "executes_correctly",
    "execution_fails",
    "generate_password",
    "arg_was_passed",
    "kwargs_to_options",
    "Logger",
    "VerboseLogger",
    "NoopLogger",
    "noop",
    "dump_set_as_list",
    "KEY_ENTER",
    "KEY_ARROWUP",
    "KEY_ARROWDOWN",
    "print_box",
    "interactive_selected_checkbox_values",
    "interactive_selected_radio_value",
    "yaml_loads",
    "dc_config",
    "print_aligned",
    "flatten",
    "shorten",
    "fabric_read",
    "fabric_read_bytes",
    "fabric_write",
]
