import sys
import pathlib
from invoke import Program, Collection
from .__about__ import __version__
from . import tasks
import importlib

# https://docs.pyinvoke.org/en/stable/concepts/library.html

collection = Collection.from_module(tasks)

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
