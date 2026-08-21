"""
Which release tool owns a project, and everything edwh asks of vommit.

Detection is edwh's own because it has to answer "should I offer to install
vommit?" before vommit exists; every other call in here goes to vommit. Those
imports are deferred on purpose -- the extra is optional, so importing at module
level would make edwh itself unimportable without it.
"""

import tomllib
import typing as t
from contextlib import contextmanager
from importlib.metadata import PackageNotFoundError, requires
from pathlib import Path

import keyring
import keyring.errors
import tomlkit
from ewok import Context
from packaging.requirements import InvalidRequirement, Requirement
from termcolor import cprint

# Where each tool keeps its configuration.
PSR_KEY = ("tool", "semantic_release")
VOMMIT_KEY = ("tool", "vommit")
# Our own opt-out, alongside [tool.edwh.lint].
PIN_KEY = ("tool", "edwh", "release")

# edwh's PyPI token, as `plugin.authenticate` has always stored it.
EDWH_KEYRING_SERVICE = "edwh"
EDWH_KEYRING_USERNAME = "pypi"

# Only used when edwh's metadata cannot be read, i.e. an uninstalled source tree.
VOMMIT_FALLBACK_SPECIFIER = ">=0.1.1,<1"

PYPROJECT = Path("pyproject.toml")

type Backend = t.Literal["vommit", "psr", "none"]


def _load(pyproject: Path) -> dict[str, t.Any]:
    """
    The pyproject as a plain dict, or empty when it is missing or unreadable.

    Unreadable counts as empty on purpose: a broken pyproject is a problem for
    the build backend to report, not a reason for `plugin.release` to traceback
    before it has said anything useful.
    """
    if not pyproject.exists():
        return {}

    try:
        return tomllib.loads(pyproject.read_text())
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError):
        return {}


def _nested(document: t.Mapping[str, t.Any], path: t.Sequence[str]) -> t.Any:
    """
    Follow a dotted key path, returning None as soon as it stops being a table.
    """
    current: t.Any = document
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def has_psr_config(pyproject: Path = PYPROJECT) -> bool:
    """
    Whether this project still carries a [tool.semantic_release] table.
    """
    return isinstance(_nested(_load(pyproject), PSR_KEY), dict)


def has_vommit_config(pyproject: Path = PYPROJECT) -> bool:
    """
    Whether this project carries a [tool.vommit] table.

    Deliberately not `vommit.config.Config.has_pyproject_config`: this question
    gets asked while vommit may not be importable yet.
    """
    return isinstance(_nested(_load(pyproject), VOMMIT_KEY), dict)


def pinned_backend(pyproject: Path = PYPROJECT) -> str | None:
    """
    The backend this project has been pinned to, if any.

        [tool.edwh.release]
        backend = "psr"
    """
    pin = _nested(_load(pyproject), PIN_KEY)
    if not isinstance(pin, dict):
        return None

    backend = pin.get("backend")
    return backend if isinstance(backend, str) else None


def detect_backend(pyproject: Path = PYPROJECT) -> Backend:
    """
    Which tool should release this project.

    A present [tool.vommit] wins over a pin, so migrating by hand is honoured
    without also having to remove the opt-out. Otherwise a pin is final -- that
    is the whole point of answering "never" -- and only then does a psr config
    lead to the migration offer.
    """
    if has_vommit_config(pyproject):
        return "vommit"

    match pinned_backend(pyproject):
        case "vommit":
            # pinned to vommit but not configured for it yet: setup, not psr
            return "none"
        case "psr":
            return "psr"

    return "psr" if has_psr_config(pyproject) else "none"


@contextmanager
def _edit(pyproject: Path) -> t.Iterator[tomlkit.TOMLDocument]:
    """
    Edit a pyproject in place, keeping its comments and formatting.

    Written back on a clean exit only, so a failure part-way leaves the file
    as it was rather than half-updated.
    """
    document = tomlkit.parse(pyproject.read_text()) if pyproject.exists() else tomlkit.document()

    yield document

    pyproject.write_text(tomlkit.dumps(document))


def _table(document: tomlkit.TOMLDocument, path: t.Sequence[str]) -> t.Any:
    """
    Reach (creating as needed) the table at a dotted key path.
    """
    current: t.Any = document
    for key in path:
        if key not in current:
            current[key] = tomlkit.table()
        current = current[key]

    return current


def pin_backend(backend: Backend, pyproject: Path = PYPROJECT) -> None:
    """
    Record the release backend in the project, so we stop asking.
    """
    with _edit(pyproject) as document:
        _table(document, PIN_KEY)["backend"] = backend


class VommitTasks(t.Protocol):
    """
    The vommit tasks edwh calls, and the arguments it calls them with.

    Spelled out rather than typed as a module, so a wrong keyword is a type
    error here instead of an AttributeError during someone's release.
    `tests/test_release_backend.py` checks the real signatures still match.
    """

    def setup(self, c: Context, /, *, project_dir: str) -> None: ...

    def migrate(self, c: Context, /, *, project_dir: str) -> None: ...

    def bump(
        self,
        c: Context,
        /,
        *,
        major: bool = False,
        minor: bool = False,
        patch: bool = False,
        prerelease: bool = False,
        noop: bool = False,
    ) -> str | None: ...

    def release(
        self,
        c: Context,
        /,
        *,
        major: bool = False,
        minor: bool = False,
        patch: bool = False,
        prerelease: bool = False,
        noop: bool = False,
        yes: bool = False,
    ) -> str | None: ...


def vommit_tasks() -> VommitTasks | None:
    """
    vommit's tasks, or None when the `edwh[vommit]` extra isn't installed.

    They take a Context and are callable in-process, which is why vommit is a
    dependency rather than a tool we shell out to: `bump` hands back the new
    version instead of us regex-scraping it out of another process' stderr.
    """
    try:
        from vommit import tasks
    except ImportError:
        return None

    return t.cast(VommitTasks, tasks)


def vommit_configured(pyproject: Path = PYPROJECT) -> bool:
    """
    Whether vommit ended up with a config here, according to vommit.

    Unlike `has_vommit_config`, this needs vommit installed -- it is for after
    the migrator has run, when it is.
    """
    from vommit.config import Config

    return Config.has_pyproject_config(pyproject)


def vommit_project_warnings(root: Path = Path()) -> list[str]:
    """
    vommit's verdict on this project's build configuration, or nothing.

    Only needed on the deprecated psr path: a vommit release prints these
    itself. Delegated rather than reimplemented -- these checks used to live
    here, and two copies of "is this project still on hatchling" is how the two
    packages end up recommending different things. Empty when the extra is
    absent, or when it predates the checks.
    """
    try:
        from vommit.build import project_warnings
        from vommit.config import Config
    except ImportError:
        return []

    try:
        return [warning.message for warning in project_warnings(root, Config.from_pyproject(root))]
    except Exception:
        # a warning about the build is never worth failing a release over
        return []


def vommit_specifier() -> str:
    """
    The version range the `vommit` extra declares.

    Read from edwh's metadata rather than written down twice, so widening the
    extra cannot leave the install prompt behind on the old range. The fallback
    covers a source tree that was never installed, whose metadata is absent.
    """
    try:
        declared = requires("edwh") or ()
    except PackageNotFoundError:
        return VOMMIT_FALLBACK_SPECIFIER

    for requirement in declared:
        try:
            parsed = Requirement(requirement)
        except InvalidRequirement:
            continue

        if parsed.name == "vommit" and parsed.marker and parsed.marker.evaluate({"extra": "vommit"}):
            return str(parsed.specifier)

    return VOMMIT_FALLBACK_SPECIFIER


def vommit_token_complaint(token: str) -> str | None:
    """
    vommit's verdict on a token's format, or None when it has nothing to say.

    Delegated rather than re-checked here: vommit already knows what a usable
    token looks like, and its message says more than "should start with pypi-".
    """
    try:
        from vommit.auth import check_format
        from vommit.errors import VommitError
    except ImportError:
        return None

    try:
        check_format(token)
    except VommitError as complaint:
        return str(complaint)

    return None


def edwh_pypi_token() -> str | None:
    """
    The PyPI token `plugin.authenticate` stored, or None when there is none.
    """
    try:
        return keyring.get_password(EDWH_KEYRING_SERVICE, EDWH_KEYRING_USERNAME)
    except keyring.errors.KeyringError:
        return None


def store_vommit_pypi_token(token: str) -> bool:
    """
    Put a token where vommit looks for it, without hardcoding where that is.

    `TokenStore` defaults to vommit's own service and username, so the two
    packages cannot drift apart on the name, and its keyring errors arrive
    already translated.
    """
    try:
        from vommit.auth import TokenStore
        from vommit.errors import VommitError
    except ImportError:
        return False

    try:
        TokenStore().store(token)
    except VommitError:
        # a keyring vommit cannot write to is not a reason to abort a release
        return False

    return True


def copy_pypi_token() -> bool:
    """
    Copy edwh's PyPI token into vommit's keyring, leaving edwh's entry alone.

    Keeping both means a half-finished migration can still release the old way.
    Returns whether vommit now has a token to publish with; a False is a nudge
    towards `vommit authenticate`, never a failure worth stopping for.
    """
    from .tasks import ensure_keyring_unlocked

    if not ensure_keyring_unlocked():
        cprint("Keyring unavailable; run `vommit authenticate` to store your PyPI token.", "yellow")
        return False

    token = edwh_pypi_token()
    if not token:
        cprint("No PyPI token in edwh's keyring; run `vommit authenticate` when you release.", "blue")
        return False

    if not store_vommit_pypi_token(token):
        cprint("Could not write to vommit's keyring; run `vommit authenticate` instead.", "yellow")
        return False

    cprint("Copied your PyPI token to vommit's keyring (edwh's copy is untouched).", "green")
    return True
