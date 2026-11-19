import atexit
import os
import signal
import sys
import typing as t
from importlib import import_module
from pathlib import Path

import ewok

from . import local_tasks, tasks
from .__about__ import __version__
from .helpers import RESULT_FILE_ENV, TaskAborted, get_input_mode, write_task_result


# https://docs.pyinvoke.org/en/stable/concepts/library.html
class EddieApp(ewok.App):
    # = fabric.Fab = invoke.Program

    @staticmethod
    def _activate_own_venv() -> None:
        """Activate the virtual environment that provides the edwh executable."""
        if sys.prefix == sys.base_prefix:
            return

        os.environ["VIRTUAL_ENV"] = sys.prefix
        bin_dir = str(Path(sys.executable).parent)
        path = os.environ.get("PATH", "")
        path_parts = (part for part in path.split(os.pathsep) if part != bin_dir)
        os.environ["PATH"] = os.pathsep.join(filter(None, (bin_dir, *path_parts)))

    def _fix_invoke_terminal_corruption(self) -> None:
        """
        Restore TTY settings after Invoke commands using pty=True.

        Invoke's pty mode often leaves the terminal in a corrupted state
        (broken echo, cursor glitches, etc.). This installs exit and signal
        handlers that always restore the original termios mode, even on
        Ctrl‑C or unexpected exceptions.
        """

        def is_tty():
            # detect if we're in a terminal; stdout may already be closed at exit (e.g. by an MCP stdio transport)
            try:
                return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
            except ValueError:
                return False

        def restore_terminal_state(*_: t.Any) -> None:
            """Safely restore the previously captured TTY settings."""
            if is_tty():
                # send ANSI clear but not if we're in a pipe
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()

        atexit.register(restore_terminal_state)

        def handle_signal(signum: int, _frame: t.Any) -> None:
            """Restore terminal state before letting signals propagate."""
            restore_terminal_state()
            if signum == signal.SIGINT:
                raise KeyboardInterrupt()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def _make_executor(self) -> t.Any:
        """Build the executor the same way `invoke.Program.execute` does."""
        klass = self.executor_class
        if config_path := self.config.tasks.executor_class:
            module_path, _, class_name = config_path.rpartition(".")
            klass = getattr(import_module(module_path), class_name)
        return klass(self.collection, self.config, self.core)

    def execute(self) -> None:
        """
        Execute the parsed tasks; with `$EDWH_RESULT_FILE` set, also report the outcome there as JSON.

        Tasks that report their own result (e.g. `lint`) take precedence, see `write_task_result`.
        A task can mark itself as failed without raising by returning a dict with `"ok": False`.
        """
        if not os.environ.get(RESULT_FILE_ENV):
            return super().execute()

        task_name = self.tasks[-1].name if self.tasks else None
        try:
            results = self._make_executor().execute(*self.tasks)
        except TaskAborted as error:
            write_task_result(task_name, ok=False, error=error)
            raise
        except SystemExit as error:
            succeeded = error.code in (0, None)
            write_task_result(task_name, ok=succeeded, error=None if succeeded else error)
            raise
        except BaseException as error:
            write_task_result(task_name, ok=False, error=error)
            raise

        result = results.get(self.collection[task_name]) if task_name else None
        ok = not (isinstance(result, dict) and result.get("ok") is False)
        write_task_result(task_name, ok=ok, result=result)
        return None

    def run(self, argv: list[str] | None = None, exit: bool = True) -> None:  # noqa: A002
        """Run the application with terminal‑safety fixes enabled."""
        self._activate_own_venv()
        self._fix_invoke_terminal_corruption()
        return super().run(argv=argv, exit=exit)

    def parse_tasks(self) -> None:
        """Mark `setup` as non-interactive when an unattended input mode is active."""
        super().parse_tasks()
        if get_input_mode() == "interactive":
            return

        for context in self.tasks:
            # identity instead of name, so aliases match and `worktree.setup` etc. don't
            if self.collection[context.name] is tasks.setup:
                # Ewok forwards the parsed arguments to plugin setup hooks, including their input policy.
                context.args["non-interactive"].value = True

    def run_fmt(self, argv: list[str] | None = None, exit: bool = True):  # noqa: A002
        """
        Process arguments for the fmt command with special handling:
        - `ew-fmt` == `ew fmt`
        - `ew-fmt file1` == `ew fmt --file file1`
        - `ew-fmt file1 file2` == `ew fmt --file file1 fmt --file file2`
        """
        self._activate_own_venv()
        argv = argv or sys.argv[1:]

        # Filter out any 'fmt' arguments to prevent duplicates
        argv = [arg for arg in argv if arg != "fmt"]

        # Convert each argument to fmt --file arg format using list comprehension;
        # if no files specified, just run fmt command
        argv = [item for arg in argv for item in ["fmt", "--file", arg]] if argv else ["fmt"]

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
