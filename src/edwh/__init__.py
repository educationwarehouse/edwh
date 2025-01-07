"""
This file exposes some functions so this tool can be used as a library.
"""

# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT

import warnings

from cryptography.utils import CryptographyDeprecationWarning

warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)

from . import tasks  # noqa E402 - import has to come after warning filter
from .constants import DOCKER_COMPOSE  # noqa E402  - import has to come after warning filter
from .helpers import (  # noqa E402  - import has to come after warning filter
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
from .improved_invoke import ImprovedTask, improved_task  # noqa E402  - import has to come after warning filter
from .tasks import (  # noqa E402  - import has to come after warning filter
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
    "KEY_ARROWDOWN",
    "KEY_ARROWUP",
    "KEY_ENTER",
    "AnyDict",
    "ImprovedTask",
    "Logger",
    "NoopLogger",
    "Task",
    "TomlConfig",
    "VerboseLogger",
    "add_alias",
    "arg_was_passed",
    "check_env",
    "confirm",
    "dc_config",
    "dump_set_as_list",
    "executes_correctly",
    "execution_fails",
    "fabric_read",
    "fabric_read_bytes",
    "fabric_write",
    "flatten",
    "generate_password",
    "get_env_value",
    "get_task",
    "improved_task",
    "interactive_selected_checkbox_values",
    "interactive_selected_radio_value",
    "kwargs_to_options",
    "noop",
    "print_aligned",
    "print_box",
    "read_dotenv",
    "set_env_value",
    "shorten",
    "task",
    "task_for_namespace",
    "tasks",
    "yaml_loads",
]
