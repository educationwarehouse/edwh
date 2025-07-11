import sys

import ewok

from . import local_tasks, tasks
from .__about__ import __version__


# https://docs.pyinvoke.org/en/stable/concepts/library.html
class EddieApp(ewok.App):
    # = fabric.Fab = invoke.Program

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


program = EddieApp(
    "edwh",
    version=__version__,
    core_module=tasks,
    extra_modules=(local_tasks,),
    plugin_entrypoint=("edwh", "edwh.tasks"),
)
