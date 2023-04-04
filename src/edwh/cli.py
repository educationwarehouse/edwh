import sys
import pathlib
from invoke import Program, Collection
from .__about__ import __version__
from . import tasks
import importlib

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

import os
print('plugins:',discovered_plugins)

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
        if 'No module named \'tasks\'' not in str(e):
            raise e
sys.path = old_path




program = Program(namespace=collection, version=__version__)
