import importlib
import importlib.util
import os
import sys
import typing
import warnings
from importlib.metadata import entry_points
from pathlib import Path

from fabric import Config, Executor
from fabric.main import Fab
from invoke import Argument, Call, Collection
from termcolor import cprint

from . import tasks
from .__about__ import __version__

# https://docs.pyinvoke.org/en/stable/concepts/library.html

collection = Collection.from_module(tasks)


### extra's tasks ###
def include_plugins() -> None:
    try:
        discovered_plugins = entry_points(group="edwh.tasks")
    except Exception as e:
        warnings.warn(f"Error locating plugins: {e}")
        return

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
def include_packaged_plugins() -> None:
    from . import local_tasks

    tasks_dir = Path(local_tasks.__file__).parent
    discovered_plugins = os.listdir(tasks_dir)
    discovered_plugins = [_.removesuffix(".py") for _ in discovered_plugins if not _.startswith("_")]
    for plugin in discovered_plugins:
        module = importlib.import_module(f".local_tasks.{plugin}", package="edwh")
        plugin_collection = Collection.from_module(module)
        collection.add_collection(plugin_collection, plugin)


### tasks in user cwd ###
def include_cwd_tasks() -> None:
    old_path = sys.path[:]

    for _path in [".", "..", "../.."]:
        path = Path(_path)
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


def collection_from_abs_path(path: str, name: str) -> typing.Optional[Collection]:
    try:
        if spec := importlib.util.spec_from_file_location(name, path):
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return Collection.from_module(module)
        else:
            return None

    except Exception as e:
        cprint(f"Failed to include personal plugin {name}: {e}", file=sys.stderr, color="yellow")
        return None


### custom ~/.config/edwh/tasks.py and ~/.config/edwh/namespace.tasks.py commands
def include_personal_tasks() -> None:
    config = Path.home() / ".config/edwh"
    config.mkdir(exist_ok=True, parents=True)

    # tasks.py - special case, add to global namespace!
    if any(config.glob("*.py")):
        config_path = str(config)
        if config_path not in sys.path:
            sys.path.append(config_path)

    personal_tasks = config / "tasks.py"
    if personal_tasks.exists() and (personal_collection := collection_from_abs_path(str(personal_tasks), "_personal_")):
        collection.tasks |= personal_collection.tasks

    # namespace.tasks.py:
    for path in set(config.glob("*.tasks.py")):
        prefix = path.stem.split(".")[0]

        if plugin_collection := collection_from_abs_path(str(path), prefix):
            collection.add_collection(plugin_collection, prefix)


def include_other_project_tasks() -> None:
    for file in Path().glob("*.tasks.py"):
        namespace = file.stem.split(".")[0]

        spec = importlib.util.spec_from_file_location(
            name=namespace,  # note that ".test" is not a valid module name
            location=file,
        )

        if not (spec and spec.loader):
            continue

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # module = importlib.import_module(file, package="edwh")
        plugin_collection = Collection.from_module(module)
        collection.add_collection(plugin_collection, namespace)


class CustomExecutor(Executor):  # type: ignore
    def expand_calls(self, calls: list[Call], apply_hosts: bool = True) -> list[Call]:
        # always apply hosts (so pre and post are also executed remotely)
        apply_hosts = True
        return typing.cast(list[Call], super().expand_calls(calls, apply_hosts))


class ImprovedFab(Fab):
    # = Program

    # Define all the no-flags in one place for reuse
    CUSTOM_FLAGS = {
        "no-local": "Skip importing ./tasks.py",
        "no-plugins": "Skip importing plugins from entry points",
        "no-packaged": "Skip importing packaged plugins from edwh/local_tasks",
        "no-personal": "Skip importing personal tasks from ~/.config/edwh",
        "no-project": "Skip importing *.tasks.py files from the current project",
    }

    def core_args(self):
        return super().core_args() + [
            Argument(
                names=(name,),
                kind=bool,
                help=help_text,
            )
            for name, help_text in self.CUSTOM_FLAGS.items()
        ]

    def print_task_help(self, name: str):
        for flag, arg in self.parser.contexts[name].flags.items():
            # invoke's help uses arg.attr_name instead of flag (key) so patch here:
            arg.attr_name = flag.strip("-")
        return super().print_task_help(name)

    def parse_collection(self):
        import_local = not self.args["no-local"].value
        import_plugins = not self.args["no-plugins"].value
        import_packaged = not self.args["no-packaged"].value
        import_personal = not self.args["no-personal"].value
        import_project = not self.args["no-project"].value

        if import_plugins:
            include_plugins()  # pip plugins
        if import_packaged:
            include_packaged_plugins()  # from src.edwh.local_tasks
        if import_local:
            include_cwd_tasks()  # from tasks.py and ../tasks.py etc.
        if import_project:
            include_other_project_tasks()  # *.tasks.py in current project
        if import_personal:
            include_personal_tasks()
        return super().parse_collection()

    def run_fmt(self, argv: list[str] = None, exit: bool = True):
        """
        Process arguments for the fmt command with special handling:
        - `ew-fmt` == `ew fmt`
        - `ew-fmt file1` == `ew fmt --file file1`
        - `ew-fmt file1 file2` == `ew fmt --file file1 fmt --file file2`
        """
        argv = argv or sys.argv[1:]

        # Filter out any 'fmt' arguments to prevent duplicates
        argv = [arg for arg in argv if arg != "fmt"]

        if not argv:
            # No files specified, just run fmt command
            argv = ["fmt"]
        else:
            # Convert each argument to fmt --file arg format using list comprehension
            argv = [item for arg in argv for item in ["fmt", "--file", arg]]

        # Add all no_flags at the beginning
        argv = [f"--{flag}" for flag in self.CUSTOM_FLAGS] + argv

        return super().run(argv, exit)


# ExtendableFab is not used right now
program = ImprovedFab(
    executor_class=CustomExecutor,
    config_class=Config,
    namespace=collection,
    version=__version__,
)
