import importlib
import os
import pathlib
import sys
import warnings

from invoke import Collection
from fabric.main import Fab  # instanceof invoke.Program
from fabric import Config, Executor

from . import tasks
from .__about__ import __version__

# https://docs.pyinvoke.org/en/stable/concepts/library.html

collection = Collection.from_module(tasks)

if sys.version_info < (3, 10):
    from importlib_metadata import entry_points
else:
    from importlib.metadata import entry_points


### extra's tasks ###
def include_plugins():
    discovered_plugins = entry_points(group='edwh.tasks')
    for plugin in discovered_plugins:
        plugin_module = plugin.load()
        plugin_collection = Collection.from_module(plugin_module)
        collection.add_collection(plugin_collection, plugin.name)


### included 'plugins' in edwh/local_tasks ###
def include_packaged_plugins():
    from . import local_tasks
    from .local_tasks import plugin

    tasks_dir = os.path.dirname(local_tasks.__file__)
    discovered_plugins = os.listdir(tasks_dir)
    discovered_plugins = [_.removesuffix(".py") for _ in discovered_plugins if not _.startswith("_")]
    for plugin in discovered_plugins:
        module = importlib.import_module(f'.local_tasks.{plugin}', package="edwh")
        plugin_collection = Collection.from_module(module)
        collection.add_collection(plugin_collection, plugin)


### tasks in user cwd ###
def include_cwd_tasks():
    old_path = sys.path[:]

    for path in ['.', '..', '../..']:
        path = pathlib.Path(path)
        sys.path = [str(path)] + old_path
        try:
            import tasks as local_tasks

            local = Collection.from_module(local_tasks)
            collection.add_collection(local, 'local')
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

program = Fab(
    executor_class=Executor,
    config_class=Config,
    namespace=collection,
    version=__version__,
)
