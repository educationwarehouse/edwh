"""
This file exposes some functions so this tool can be used as a library.
"""

# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT

from ewok import Task, task
from ewok.monkey import monkeypatch_invoke

monkeypatch_invoke("edwh")

from . import tasks
from .constants import DOCKER_COMPOSE
from .health import (
    HealthLevel,
    HealthStatus,
    docker_inspect,
    find_container_ids,
    find_containers_ids,
    get_healths,
)
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
from .meta import is_installed
from .tasks import (
    TomlConfig,
    check_env,
    get_env_value,
    get_task,
    read_dotenv,
    set_env_value,
    task_for_namespace,
)

ImprovedTask = Task
improved_task = task

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
    "is_installed",
    "HealthLevel",
    "get_healths",
    "find_container_ids",
    "find_containers_ids",
    "HealthStatus",
    "docker_inspect",
]
