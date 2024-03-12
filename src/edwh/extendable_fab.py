from fabric.main import Fab
from invoke import Argument
from typing_extensions import deprecated


@deprecated
class ExtendableFab(Fab):
    _core_args: list[Argument] = []  # noqa RUF012: class variable, can be filled without instance

    def __init__(
        self,
        version=None,
        namespace=None,
        name=None,
        binary=None,
        loader_class=None,
        executor_class=None,
        config_class=None,
        binary_names=None,
    ):
        super().__init__(
            version=version,
            namespace=namespace,
            name=name,
            binary=binary,
            loader_class=loader_class,
            executor_class=executor_class,
            config_class=config_class,
            binary_names=binary_names,
        )

        self._core_args.extend(super().core_args())  # load initial ones

    @classmethod
    def core_args(cls):
        # super already called in init.
        return cls._core_args

    @classmethod
    def add_core_arg(cls, arg: Argument):
        cls._core_args.append(arg)
