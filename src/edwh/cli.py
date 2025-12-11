import atexit
import contextlib
import signal
import sys
import termios
import typing as t

import ewok

from . import local_tasks, tasks
from .__about__ import __version__


# https://docs.pyinvoke.org/en/stable/concepts/library.html
class EddieApp(ewok.App):
    # = fabric.Fab = invoke.Program

    def _fix_invoke_terminal_corruption(self) -> None:
        """
        Restore TTY settings after Invoke commands using pty=True.

        Invoke's pty mode often leaves the terminal in a corrupted state
        (broken echo, cursor glitches, etc.). This installs exit and signal
        handlers that always restore the original termios mode, even on
        Ctrl‑C or unexpected exceptions.
        """
        tty_fd = sys.stdin.fileno()
        orig_termios = termios.tcgetattr(tty_fd)

        def restore_terminal_state(*_: t.Any) -> None:
            """Safely restore the previously captured TTY settings."""
            with contextlib.suppress(Exception):
                termios.tcsetattr(tty_fd, termios.TCSADRAIN, orig_termios)

        atexit.register(restore_terminal_state)

        def handle_signal(signum: int, _frame: t.Any) -> None:
            """Restore terminal state before letting signals propagate."""
            restore_terminal_state()
            if signum == signal.SIGINT:
                raise KeyboardInterrupt()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def __call__(self, argv: t.Optional[list[str]] = None, exit: bool = True) -> None:
        """Run the application with terminal‑safety fixes enabled."""
        self._fix_invoke_terminal_corruption()
        return super().__call__(argv=argv, exit=exit)

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
