"""
# usage:
>>> from .improved_invoke import improved_task as task # noqa
>>> @task(flags={})
>>> def something(): ...
"""

import functools
import inspect
import typing
import warnings
from typing import Any, Callable, Iterable, Optional

from invoke.context import Context
from invoke.tasks import Task as InvokeTask
from invoke.tasks import task as invoke_task
from typing_extensions import Unpack

from .helpers import AnyDict

TaskFn: typing.TypeAlias = typing.Callable[[Context], Any] | typing.Callable[..., Any]

P = typing.ParamSpec("P")
R = typing.TypeVar("R")


class TaskOptions(typing.TypedDict, total=False):
    name: Optional[str]
    aliases: Iterable[str]
    positional: Optional[Iterable[str]]
    optional: Iterable[str]
    default: bool
    auto_shortflags: bool
    help: Optional[AnyDict]
    pre: Optional[list[TaskFn]]
    post: Optional[list[TaskFn]]
    autoprint: bool
    iterable: Optional[Iterable[str]]
    incrementable: Optional[Iterable[str]]
    flags: dict[str, Iterable[str]] | None
    hookable: bool


class TaskCallable(typing.Protocol):
    def __call__(
        self, **_: Unpack[TaskOptions]
    ) -> Callable[
        [Callable[P, R]],
        Callable[P, R],
    ]: ...


class ImprovedTask(InvokeTask[TaskCallable]):
    """
    Improved version of Invoke Task where you can set custom flags for command line arguments.
    This allows you to specify aliases, rename (e.g. --json for 'as_json')  and custom short flags (--exclude = -x)
    """

    _flags: dict[str, list[str]]

    def __init__(
        self,
        body: TaskCallable,
        name: Optional[str] = None,
        aliases: Iterable[str] = (),
        positional: Optional[Iterable[str]] = None,
        optional: Iterable[str] = (),
        default: bool = False,
        auto_shortflags: bool = True,
        help: Optional[AnyDict] = None,  # noqa
        pre: Optional[list[TaskFn]] = None,
        post: Optional[list[TaskFn]] = None,
        autoprint: bool = False,
        iterable: Optional[Iterable[str]] = None,
        incrementable: Optional[Iterable[str]] = None,
        # new:
        flags: dict[str, Iterable[str]] | None = None,
        hookable: bool = False,
    ):
        self._flags = flags or {}
        self.hookable = hookable

        super().__init__(
            body=body,
            name=name,
            aliases=tuple(aliases),
            positional=positional,
            optional=optional,
            default=default,
            auto_shortflags=auto_shortflags,
            help=help,
            pre=pre,  # type: ignore
            post=post,  # type: ignore
            autoprint=autoprint,
            iterable=iterable,
            incrementable=incrementable,
        )

    def arg_opts(self, name: str, default: str, taken_names: Iterable[str]) -> AnyDict:
        """Get argument options.

        Args:
            name (str): The name of the argument.
            default (str): The default value of the argument.
            taken_names (Iterable[str]): Names that have already been taken.

        Returns:
            AnyDict: A dictionary of argument options.
        """
        opts = super().arg_opts(name=name, default=default, taken_names=set(taken_names))

        if flags := self._flags.get(name):
            opts["names"] = list(flags)

        return opts

    def _execute_subtask(self, ctx: Context, task: TaskFn, *args, **kwargs):
        """Execute a subtask with provided context and arguments.

        Args:
            ctx (Context): The context to pass to the task.
            task (TaskFn): The task function to execute.
            *args: Positional arguments for the task.
            **kwargs: Keyword arguments for the task.
        """
        sig = inspect.signature(task)
        task_args = [ctx]  # Start with the context
        task_kwargs = {}

        # Collect positional arguments
        param_names = list(sig.parameters.keys())
        for i, param in enumerate(param_names[1:], start=0):  # Skip 'ctx'
            if i < len(args):
                task_args.append(args[i])
            elif sig.parameters[param].default is sig.empty:
                raise ValueError(f"Missing required argument: {param}")

        # Collect keyword arguments
        for param in param_names[1:]:
            if param in kwargs:
                task_kwargs[param] = kwargs[param]

        # Call the task with the prepared arguments
        return task(*task_args, **task_kwargs)

    def _run_hooks(self, ctx: Context, *args, **kwargs):
        """Run hooks for the current instance.

        Args:
            ctx (Context): The context to pass to the hooks.
            *args: Positional arguments for the hooks.
            **kwargs: Keyword arguments for the hooks.
        """
        for namespace, task in find_task_across_namespaces(self.name).items():
            if task is not self:
                try:
                    subresult = self._execute_subtask(ctx, task, *args, **kwargs)
                except Exception as e:
                    warnings.warn(
                        f"Failed running subtask {namespace}.{task.name}: {e}.", source=e, category=RuntimeWarning
                    )
                    continue

                if isinstance(ctx["result"], dict) and isinstance(subresult, dict):
                    ctx["result"].update(subresult)
                elif subresult is not None:
                    ctx["result"] = subresult

    def __call__(self, ctx: Context, *args, **kwargs):
        """Invoke the callable instance.

        Args:
            ctx (Context): The context to pass.
            *args: Positional arguments.
            **kwargs: Keyword arguments.

        Returns:
            The result of the superclass call.
        """
        ctx["result"] = ctx.get("result") or {}
        result = super().__call__(ctx, *args, **kwargs)

        if isinstance(ctx["result"], dict) and isinstance(result, dict):
            ctx["result"].update(result)
        elif result is not None:
            ctx["result"] = result

        if self.hookable:
            self._run_hooks(ctx, *args, **kwargs)

        return ctx["result"]


def find_task_across_namespaces(name: str) -> dict[str, ImprovedTask]:
    from .cli import collection

    return {ns.name: task for ns in collection.collections.values() if (task := ns.tasks.get(name))}


improved_task: TaskCallable = functools.partial(invoke_task, klass=ImprovedTask)

__all__ = ["ImprovedTask", "improved_task"]
