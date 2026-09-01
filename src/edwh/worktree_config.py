"""
Pure helpers for `ew worktree`: naming, the `[worktree]` config section, and the .env rewrite.

Kept free of Context/docker/git so it can be unit tested without a repository.
"""

import fnmatch
import os
import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_COPY = [".env", ".toml"]
# COMPOSE_PROJECT_NAME beats the directory name, so a copied one would fuse the two environments
DEFAULT_RESET = ["*_PORT", "SCHEMA_VERSION", "COMPOSE_PROJECT_NAME"]
DEFAULT_ENV = {"PROJECT": "{repo}-{slug}"}
DEFAULT_SEED = "fresh"

# tiny image used to copy one volume into another; docker has no native volume clone
CLONE_IMAGE = "alpine"

T_Seed = t.Literal["fresh", "clone", "devdb"]
SEEDS: tuple[str, ...] = t.get_args(T_Seed)

# gitignore entries that are never worth copying into a worktree
COPY_BLOCKLIST = (
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    ".idea",
    ".vscode",
    ".ipynb_checkpoints",
    "*.pyc",
    "*.swp",
    ".fuse_*",
)


def slugify(branch: str) -> str:
    """
    Branch name to a directory- and docker-safe slug.

    >>> slugify("feature/EW-Worktree")
    'feature-ew-worktree'
    """
    slug = branch.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def worktree_dirname(repo: str, branch: str) -> str:
    """
    Directory name for a worktree: `<repo>-<slug>`, slugified.

    Flat rather than `<repo>/<slug>` so a shell prompt showing only the basename still says which
    project you are in. Slugified because compose derives its project name from this directory and
    lowercases it - keeping them identical is what makes $PROJECT, the compose project, the volume
    prefix and the container prefix all agree.
    """
    return f"{slugify(repo)}-{slugify(branch)}"


def worktree_root() -> Path:
    """
    Where worktrees live: ~/.cache/edwh/worktrees, honouring $XDG_CACHE_HOME.

    Overridden by $EDWH_WORKTREE_ROOT, or by `root` in the [worktree] config.
    """
    if override := os.environ.get("EDWH_WORKTREE_ROOT"):
        return Path(override).expanduser()

    cache_home = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(cache_home) / "edwh" / "worktrees"


@dataclass
class WorktreeConfig:
    copy: list[str] = field(default_factory=lambda: list(DEFAULT_COPY))
    reset: list[str] = field(default_factory=lambda: list(DEFAULT_RESET))
    env: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_ENV))
    seed: str = DEFAULT_SEED
    root: str = ""

    @classmethod
    def from_toml(cls, config: dict[str, t.Any] | None) -> "WorktreeConfig":
        """
        Read the [worktree] section, falling back to defaults for anything absent.

        Values are coerced to plain str/list/dict: read_toml_config hands back tomlkit objects,
        which subclass str but do not survive yaml/json serialisation.
        """
        section = (config or {}).get("worktree") or {}
        return cls(
            copy=[str(entry) for entry in (section.get("copy") or DEFAULT_COPY)],
            reset=[str(entry) for entry in (section.get("reset") or DEFAULT_RESET)],
            env={str(key): str(value) for key, value in {**DEFAULT_ENV, **(section.get("env") or {})}.items()},
            seed=str(section.get("seed") or DEFAULT_SEED),
            root=str(section.get("root") or ""),
        )

    def to_toml(self) -> dict[str, t.Any]:
        section: dict[str, t.Any] = {
            "copy": self.copy,
            "reset": self.reset,
            "seed": self.seed,
            "env": self.env,
        }
        if self.root:
            section["root"] = self.root
        return section

    def root_path(self) -> Path:
        return Path(self.root).expanduser() if self.root else worktree_root()


def dest_volume_name(volume: str, src_project: str, dst_project: str) -> str | None:
    """
    The name the same compose volume gets in another project, or None if it does not travel.

    Compose prefixes declared volumes with the project name (the directory), so `demo_pgdata`
    becomes `feature-login_pgdata`. Names without that prefix are anonymous volumes (recreated
    empty anyway) or external ones (shared on purpose) - both must be left alone.
    """
    prefix = f"{src_project}_"
    if not volume.startswith(prefix):
        return None

    return f"{dst_project}_{volume[len(prefix) :]}"


def matches_reset(key: str, patterns: t.Iterable[str]) -> bool:
    """Does this .env key match any of the reset globs? Case insensitive, like .env keys."""
    key = key.upper()
    return any(fnmatch.fnmatch(key, pattern.upper()) for pattern in patterns)


def keys_to_reset(env: t.Mapping[str, str], patterns: t.Iterable[str]) -> list[str]:
    return [key for key in env if matches_reset(key, patterns)]


# a branch that shows what slugify does, for illustrating templates before one has been chosen
EXAMPLE_BRANCH = "feature/login"

PLACEHOLDERS = ("value", "repo", "branch", "slug")


class TemplateError(ValueError):
    """A [worktree.env] template a user typed does not make sense."""


def render_template(template: str, *, value: str, repo: str, branch: str, slug: str) -> str:
    """
    Expand one [worktree.env] template, with an error a human can act on.

    `str.format` would raise a bare KeyError naming only the bad placeholder, and it would do so
    while creating a worktree - long after the template was typed.
    """
    try:
        return template.format(value=value, repo=repo, branch=branch, slug=slug)
    except KeyError as e:
        known = ", ".join(f"{{{name}}}" for name in PLACEHOLDERS)
        raise TemplateError(f"unknown placeholder {{{e.args[0]}}} - available: {known}") from e
    except (IndexError, ValueError) as e:
        raise TemplateError(f"malformed template ({e}); use {{value}}, or {{{{ for a literal brace") from e


def example_values(repo: str, current_value: str = "<current value>", branch: str = EXAMPLE_BRANCH) -> dict[str, str]:
    """What each placeholder would expand to, for showing next to a prompt."""
    return {"value": current_value, "repo": repo, "branch": branch, "slug": slugify(branch)}


def render_env_templates(
    env: t.Mapping[str, str],
    templates: t.Mapping[str, str],
    *,
    repo: str,
    branch: str,
    slug: str,
) -> dict[str, str]:
    """
    Expand the [worktree.env] templates against the source .env.

    {value} is the value the key had in the source; a key absent there resolves {value} to "".
    Templates for keys that do not exist in the source are still applied, so a project can
    introduce a key that only worktrees have.
    """
    return {
        key: render_template(template, value=env.get(key, ""), repo=repo, branch=branch, slug=slug)
        for key, template in templates.items()
    }


@dataclass
class EnvKeyCandidate:
    """One .env key, with why it does (or does not) look environment-specific."""

    key: str
    reasons: list[str] = field(default_factory=list)
    suggested: bool = False

    @property
    def label(self) -> str:
        return f"{self.key:<28} {' · '.join(self.reasons)}".rstrip()


def classify_env_keys(
    env: t.Mapping[str, str],
    others: t.Iterable[t.Mapping[str, str]],
    published_ports: t.Collection[str] = (),
    rewritten: t.Collection[str] = (),
) -> list[EnvKeyCandidate]:
    """
    Work out which .env keys have to be regenerated per environment.

    Three signals, cheapest first:

    * the key is a published port in docker-compose -> two environments cannot both bind it;
    * its value differs across the environments already on this machine -> it is per-environment
      by construction, and this reads back the judgement calls already made by hand;
    * it is identical everywhere -> shared config, copy it verbatim.

    Keys already handled by [worktree.env] are listed but never suggested: rewriting and resetting
    the same key would fight each other.

    Candidates come back most-likely first, so the picker can show the interesting ones on screen.
    """
    others = [dict(other) for other in others]

    candidates = []
    for key, value in env.items():
        candidate = EnvKeyCandidate(key)

        if key in rewritten:
            candidate.reasons.append("handled by [worktree.env]")
            candidates.append(candidate)
            continue

        if key in published_ports:
            candidate.reasons.append("published port")
            candidate.suggested = True

        elsewhere = [other[key] for other in others if key in other]
        if elsewhere:
            differing = sum(1 for other in elsewhere if other != value)
            total = len(elsewhere) + 1
            if differing:
                candidate.reasons.append(f"differs in {differing + 1} of {total} envs")
                candidate.suggested = True
            else:
                candidate.reasons.append(f"identical in {total} envs")

        candidates.append(candidate)

    candidates.sort(key=lambda c: (not c.suggested, c.key))
    return candidates


def published_port_keys(compose: t.Mapping[str, t.Any]) -> set[str]:
    """
    .env keys used on the *host* side of a `ports:` mapping.

    "${WEB_PORT}:80" -> {"WEB_PORT"}; "8000" or "80" alone publish a fixed port and cannot be made
    unique per environment, so they are not reported.
    """
    found: set[str] = set()

    for service in (compose.get("services") or {}).values():
        for mapping in service.get("ports") or []:
            if isinstance(mapping, dict):
                # long syntax: {published: "${WEB_PORT}", target: 80}
                host_side = str(mapping.get("published", ""))
            else:
                host_side = str(mapping).rsplit(":", 1)[0] if ":" in str(mapping) else ""

            found.update(re.findall(r"\$\{?(\w+)", host_side))

    return found


def collapse_to_globs(selected: t.Collection[str], all_keys: t.Collection[str]) -> list[str]:
    """
    Rewrite a concrete selection as globs, but only where a glob means exactly the selection.

    `*_PORT` is only used when every key ending in _PORT was selected; otherwise the literal names
    are kept. That way a port added next month is caught automatically, without a glob silently
    picking up a key that should have been copied verbatim.
    """
    selected = set(selected)
    remaining = set(selected)
    globs: list[str] = []

    suffixes = {key.rsplit("_", 1)[-1] for key in selected if "_" in key}
    for suffix in sorted(suffixes):
        family = {key for key in all_keys if key.endswith(f"_{suffix}")}
        if len(family) > 1 and family <= selected:
            globs.append(f"*_{suffix}")
            remaining -= family

    return globs + sorted(remaining)


def suggest_copy_entries(gitignore: str, root: Path) -> list[str]:
    """
    Propose which gitignored paths to carry into a worktree.

    Only entries that exist on disk right now and are not obvious build junk; those are the ones
    holding secrets and state. Negations and comments are skipped, as are globs, which cannot be
    copied as a single path.
    """
    suggestions: list[str] = []

    for raw in gitignore.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("!"):
            continue

        entry = line.lstrip("/").rstrip("/")
        if not entry or "*" in entry or entry in suggestions:
            continue
        if any(fnmatch.fnmatch(entry, pattern) or Path(entry).name == pattern for pattern in COPY_BLOCKLIST):
            continue
        if not (root / entry).exists():
            continue

        suggestions.append(entry + ("/" if (root / entry).is_dir() else ""))

    for default in DEFAULT_COPY:
        if default not in suggestions and (root / default).exists():
            suggestions.insert(0, default)

    return suggestions
