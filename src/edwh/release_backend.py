"""
Which release tool owns a project, and what it takes to move it to vommit.

`plugin.release` used to mean "run python-semantic-release". It now routes: a
project configured for vommit is released by vommit, a project still on psr is
offered a migration, and a project with neither is offered a first-time setup.
Deciding which of those applies has to work *before* vommit is installed, so
the detection here is deliberately edwh's own rather than a call into
`vommit.migrate` -- it is three key lookups, and it buys the ability to leave
vommit uninstalled on projects that will never want it. Everything downstream
of the prompt imports from vommit instead of reimplementing it.

Reads go through `tomllib` (like `enabled_lint_tools`), writes through
`tomlkit`, so a project's comments and formatting survive being pinned.
"""

import tomllib
import typing as t
from contextlib import contextmanager
from pathlib import Path

import keyring
import keyring.errors
import tomlkit
from termcolor import cprint

# Where each tool keeps its configuration.
PSR_KEY = ("tool", "semantic_release")
VOMMIT_KEY = ("tool", "vommit")
# Our own opt-out, alongside [tool.edwh.lint].
PIN_KEY = ("tool", "edwh", "release")

# edwh's PyPI token, as `plugin.authenticate` has always stored it.
EDWH_KEYRING_SERVICE = "edwh"
EDWH_KEYRING_USERNAME = "pypi"

PYPROJECT = Path("pyproject.toml")

type Backend = t.Literal["vommit", "psr", "none"]

# The psr keys that meant "do not upload"; edwh's convention set them because
# `plugin.release` did the uploading itself.
PSR_UPLOAD_KEYS = ("upload_to_repository", "upload_to_pypi")


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


def psr_uploaded(pyproject: Path = PYPROJECT) -> bool:
    """
    Whether psr itself was uploading this project to an index.

    Must be read *before* migrating, because vommit strips the table. When psr
    was not uploading, vommit's translation faithfully turns publishing off --
    and that is wrong for us, because the uploading was `plugin.release`'s job
    all along. See `enable_publishing`.
    """
    psr = _nested(_load(pyproject), PSR_KEY)
    if not isinstance(psr, dict):
        # no psr config at all: nothing was disabled, so nothing to restore
        return True

    # v7 defaulted both to true; either one set to false stopped the upload.
    return all(psr.get(key, True) is not False for key in PSR_UPLOAD_KEYS)


def vommit_publishes(pyproject: Path = PYPROJECT) -> bool:
    """
    Whether a migrated project would actually publish.
    """
    pypi = _nested(_load(pyproject), (*VOMMIT_KEY, "pypi"))
    if not isinstance(pypi, dict):
        # the section is absent, which vommit reads as enabled
        return True

    return pypi.get("enabled", True) is not False


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


def enable_publishing(pyproject: Path = PYPROJECT) -> None:
    """
    Turn vommit's publishing step back on after a migration turned it off.
    """
    with _edit(pyproject) as document:
        _table(document, (*VOMMIT_KEY, "pypi"))["enabled"] = True


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
    except ImportError:
        return False

    try:
        TokenStore().store(token)
    except Exception:
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
