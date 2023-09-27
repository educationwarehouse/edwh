import importlib
import os
import pathlib
import sys
import warnings
from importlib.metadata import entry_points

from fabric import Config, Executor
from invoke import Argument, Collection

from . import tasks
from .__about__ import __version__
from .extendable_fab import ExtendableFab  # instanceof invoke.Program

# https://docs.pyinvoke.org/en/stable/concepts/library.html

collection = Collection.from_module(tasks)


### extra's tasks ###
def include_plugins():
    try:
        discovered_plugins = entry_points(group="edwh.tasks")
    except Exception as e:
        warnings.warn(f"Error locating plugins: {e}")

    try:
        for plugin in discovered_plugins:
            try:
                plugin_module = plugin.load()
            except Exception as e:
                print(f"Error loading plugin {plugin.name}: {e}")
                continue
            plugin_collection = Collection.from_module(plugin_module)
            collection.add_collection(plugin_collection, plugin.name)
    except Exception as e:
        warnings.warn(f"Error loading plugins: {e}")


### included 'plugins' in edwh/local_tasks ###
def include_packaged_plugins():
    from . import local_tasks

    tasks_dir = os.path.dirname(local_tasks.__file__)
    discovered_plugins = os.listdir(tasks_dir)
    discovered_plugins = [_.removesuffix(".py") for _ in discovered_plugins if not _.startswith("_")]
    for plugin in discovered_plugins:
        module = importlib.import_module(f".local_tasks.{plugin}", package="edwh")
        plugin_collection = Collection.from_module(module)
        collection.add_collection(plugin_collection, plugin)


### tasks in user cwd ###
def include_cwd_tasks():
    old_path = sys.path[:]

    for path in [".", "..", "../.."]:
        path = pathlib.Path(path)
        sys.path = [str(path), *old_path]
        try:
            import tasks as local_tasks

            local = Collection.from_module(local_tasks)
            collection.add_collection(local, "local")
            break
        except ImportError as e:
            if "No module named 'tasks'" not in str(e):
                warnings.warn(
                    f"\nWARN: Could not import local tasks.py: `{e}`",
                    # ImportWarning, # <- will be ignored by most Python installations!
                    source=e,
                )
                print(file=sys.stderr)  # 1 newline padding before actual stdout content

    sys.path = old_path


include_plugins()
include_packaged_plugins()
include_cwd_tasks()

program = ExtendableFab(
    executor_class=Executor,
    config_class=Config,
    namespace=collection,
    version=__version__,
)
