"""
Pure helpers for `edwh worktree`.

The [worktree] config plus the data transformations it drives: naming, .env keys, volume names,
templates. Every function here takes its inputs as arguments and does no I/O, so it is testable
without a repository or a docker daemon.

`local_tasks/worktree.py` holds the tasks themselves and everything that talks to git, docker, the
terminal, or the step pipeline.
"""

import fnmatch
import os
import re
import typing as t
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

DEFAULT_COPY = (".env", ".toml")
# COMPOSE_PROJECT_NAME beats the directory name, so a copied one would fuse the two environments
DEFAULT_RESET = ("*_PORT", "SCHEMA_VERSION", "COMPOSE_PROJECT_NAME")
DEFAULT_ENV = {"PROJECT": "{repo}-{slug}"}
DEFAULT_SEED = "fresh"

# tiny image used to copy one volume into another; docker has no native volume clone
CLONE_IMAGE = "alpine"

T_Seed = t.Literal["fresh", "clone", "devdb"]
SEEDS: tuple[str, ...] = t.get_args(T_Seed)

# a branch that shows what slugify does, for illustrating templates before one is chosen
EXAMPLE_BRANCH = "feature/login"
PLACEHOLDERS = ("value", "repo", "branch", "slug")

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
    "*.bak",
    ".fuse_*",
)

NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
ENV_VAR_RE = re.compile(r"\$\{?(\w+)")


def slugify(branch: str) -> str:
    """
    Branch name to a directory- and docker-safe slug: "feature/EW-Worktree" -> "feature-ew-worktree".
    """
    slug = branch.strip().lower()
    slug = NON_SLUG_RE.sub("-", slug)
    return slug.strip("-")


def worktree_dirname(repo: str, branch: str) -> str:
    """
    Directory name for a worktree: `<repo>-<slug>`.

    Flat, so a prompt showing only the basename still names the project. Slugified because compose
    derives its (lowercased) project name from this directory, and keeping the two identical makes
    $PROJECT, the compose project and the volume/container prefixes agree.
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

        Values are coerced to plain str/list/dict, since read_toml_config hands back tomlkit
        objects that subclass str but do not survive serialisation.
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


def service_of(container: t.Mapping[str, t.Any]) -> str:
    """The compose service a docker-inspect payload belongs to."""
    return container.get("Config", {}).get("Labels", {}).get("com.docker.compose.service", "")


def hostingdomains(env: t.Mapping[str, str]) -> set[str]:
    """
    HOSTINGDOMAIN(S) from a .env, as a fallback for projects that do not route through traefik.

    Plural because projects disagree on the key name, and the value may be a comma separated list.
    """
    raw = env.get("HOSTINGDOMAIN") or env.get("HOSTINGDOMAINS") or ""
    return {domain.strip() for domain in raw.split(",") if domain.strip()}


def as_toml(config: WorktreeConfig) -> str:
    """Render a [worktree] section as TOML, for showing back to the user."""
    return tomlkit.dumps({"worktree": config.to_toml()})


def env_vars_in_host_labels(compose: t.Mapping[str, t.Any]) -> list[str]:
    """
    Which .env keys the traefik Host() rules depend on, and so decide hostname collisions.
    """
    found: list[str] = []
    for service in (compose.get("services") or {}).values():
        for label, value in (service.get("labels") or {}).items():
            if "Host" not in str(value):
                continue
            for name in ENV_VAR_RE.findall(f"{label}{value}"):
                if name not in found:
                    found.append(name)
    return found


def check_reset_took_effect(
    source_env: t.Mapping[str, str],
    new_env: t.Mapping[str, str],
    reset: t.Collection[str],
) -> list[str]:
    """
    Which reset keys came back with the source's value anyway.

    Deleting a key only helps when local.setup derives its default from the environment
    (`next_value`, the cwd). A constant default like "localhost" regenerates the same value, and
    both environments silently share it; such keys need a [worktree.env] template instead.
    """
    return [
        key
        for key in keys_to_reset(source_env, reset)
        if key in new_env and new_env[key] == source_env[key] and source_env[key]
    ]


def dest_volume_name(volume: str, src_project: str, dst_project: str) -> str | None:
    """
    The name a compose volume gets in another project, or None if it does not travel.

    Compose prefixes declared volumes with the project name, so `demo_pgdata` becomes
    `feature-login_pgdata`. Anything without that prefix is anonymous (recreated empty) or external
    (shared on purpose), and is left alone.
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


class TemplateError(ValueError):
    """A [worktree.env] template a user typed does not make sense."""


def render_template(template: str, *, value: str, repo: str, branch: str, slug: str) -> str:
    """
    Expand one [worktree.env] template.

    Raises TemplateError rather than the bare KeyError `str.format` would raise while creating a
    worktree, long after the template was typed.
    """
    try:
        return template.format(value=value, repo=repo, branch=branch, slug=slug)
    except KeyError as e:
        known = ", ".join(f"{{{name}}}" for name in PLACEHOLDERS)
        raise TemplateError(f"unknown placeholder {{{e.args[0]}}}; available: {known}") from e
    except (IndexError, ValueError) as e:
        hint = "use {value}, or {{ for a literal brace"
        raise TemplateError(f"malformed template ({e}); {hint}") from e


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

    {value} is the source value, or "" for a key the source lacks; such keys are still written, so
    a project can introduce one that only worktrees have.
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

    Three signals: a published port cannot be bound twice; a value that differs across the
    environments already on this machine is per-environment by construction; one that is identical
    everywhere is shared config. Keys handled by [worktree.env] are listed but never suggested,
    since rewriting and resetting the same key would fight.

    Most-likely candidates come first, so the picker shows the interesting ones on screen.
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
    .env keys on the *host* side of a `ports:` mapping: "${WEB_PORT}:80" -> {"WEB_PORT"}.

    A bare "8000" publishes a fixed port that cannot be made unique, so it is not reported.
    """
    found: set[str] = set()

    for service in (compose.get("services") or {}).values():
        for mapping in service.get("ports") or []:
            if isinstance(mapping, dict):
                # long syntax: {published: "${WEB_PORT}", target: 80}
                host_side = str(mapping.get("published", ""))
            else:
                host_side = str(mapping).rsplit(":", 1)[0] if ":" in str(mapping) else ""

            found.update(ENV_VAR_RE.findall(host_side))

    return found


def collapse_to_globs(selected: t.Collection[str], all_keys: t.Collection[str]) -> list[str]:
    """
    Rewrite a selection as globs, but only where a glob means exactly that selection.

    `*_PORT` is used only when every _PORT key was selected, so a port added later is caught too
    without a glob silently picking up a key that should have been copied verbatim.
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
    Propose which gitignored paths to carry into a worktree: the ones holding secrets and state.

    Only entries that exist on disk and are not obvious build junk. Comments, negations and globs
    are skipped, the last because they are not a single copyable path.
    """
    suggestions: list[str] = []

    for raw in gitignore.splitlines():
        line = raw.strip()
        # '#' only comments out a whole line in .gitignore, and '!' re-includes a path
        if not line or line.startswith(("#", "!")):
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
