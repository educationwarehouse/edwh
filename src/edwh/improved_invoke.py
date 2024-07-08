"""
# usage:
>>> from .improved_invoke import improved_task as task # noqa
>>> @task(flags={})
>>> def something(): ...
"""

import functools
import typing
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Union

from invoke import Task as InvokeTask
from invoke import task as invoke_task
from typing_extensions import Unpack


class ImprovedTask(InvokeTask):
    """
    Improved version of Invoke Task where you can set custom flags for command line arguments.
    This allows you to specify aliases, rename (e.g. --json for 'as_json')  and custom short flags (--exclude = -x)
    """

    _flags: dict[str, list[str]]

    def __init__(
        self,
        body: Callable,
        name: Optional[str] = None,
        aliases: Iterable[str] = (),
        positional: Optional[Iterable[str]] = None,
        optional: Iterable[str] = (),
        default: bool = False,
        auto_shortflags: bool = True,
        help: Optional[Dict[str, Any]] = None,  # noqa
        pre: Optional[Union[List[str], str]] = None,
        post: Optional[Union[List[str], str]] = None,
        autoprint: bool = False,
        iterable: Optional[Iterable[str]] = None,
        incrementable: Optional[Iterable[str]] = None,
        # new:
        flags: dict[str, list[str]] | None = None,
    ):
        self._flags = flags or {}

        super().__init__(
            body=body,
            name=name,
            aliases=tuple(aliases),
            positional=positional,
            optional=optional,
            default=default,
            auto_shortflags=auto_shortflags,
            help=help,
            pre=pre,
            post=post,
            autoprint=autoprint,
            iterable=iterable,
            incrementable=incrementable,
        )

    def arg_opts(self, name: str, default: str, taken_names: typing.Iterable[str]):
        opts = super().arg_opts(name=name, default=default, taken_names=set(taken_names))

        if flags := self._flags.get(name):
            # todo: check taken?
            #  -> currently, you get an error like
            #  'ValueError: Tried to add an argument named 't' but one already exists!'
            #  for now, you'll just have to manually set correct flags to prevent this.
            opts["names"] = flags

        return opts


P = typing.ParamSpec("P")
R = typing.TypeVar("R")


class TaskOptions(typing.TypedDict, total=False):
    name: Optional[str]
    aliases: Iterable[str]
    positional: Optional[Iterable[str]]
    optional: Iterable[str]
    default: bool
    auto_shortflags: bool
    help: Optional[Dict[str, Any]]
    pre: Optional[Union[List[str], str]]
    post: Optional[Union[List[str], str]]
    autoprint: bool
    iterable: Optional[Iterable[str]]
    incrementable: Optional[Iterable[str]]
    flags: dict[str, list[str]] | None


class TaskCallable(typing.Protocol):
    def __call__(self, **_: Unpack[TaskOptions]) -> Callable[
        [Callable[P, R]],
        Callable[P, R],
    ]: ...


improved_task: TaskCallable = functools.partial(invoke_task, klass=ImprovedTask)

__all__ = ["ImprovedTask", "improved_task"]
