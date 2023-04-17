import pathlib
import sys

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

discovered_plugins = entry_points(group='edwh.tasks')
for plugin in discovered_plugins:
    plugin_module = plugin.load()
    plugin_collection = Collection.from_module(plugin_module)
    collection.add_collection(plugin_collection, plugin.name)

# print('Discovered plugins:',[_.value.split('.')[0] for _ in discovered_plugins])

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
            raise e

sys.path = old_path

program = Fab(
    executor_class=Executor,
    config_class=Config,
    namespace=collection,
    version=__version__,
)
