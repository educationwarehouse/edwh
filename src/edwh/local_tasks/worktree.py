"""
Parallel dev environments per branch: `ew worktree <branch>`.

A git worktree on its own does not give you a working environment - our compose setups also carry
gitignored secrets, a generated .toml and database state in docker volumes. This module adds the
missing parts: it copies the config a project declares, strips the keys that must be unique, lets
the project's own `local.setup` regenerate them, and seeds the database.

The trick that keeps this small: `check_env` returns values that already exist untouched, so
removing a key from the copied .env is enough to have it recomputed - including ports, via the
existing `next_value` / `next_available_port` helpers.
"""

import asyncio
import re
import shlex
import shutil
import sys
import typing as t
from pathlib import Path

import tomlkit
import yaml
from ewok import Context, task
from termcolor import colored, cprint

from ..constants import DEFAULT_DOTENV_PATH, DEFAULT_TOML_NAME, DOCKER_COMPOSE
from ..discover import get_hosts_for_service
from ..helpers import confirm, interactive_selected_checkbox_values, interactive_selected_radio_value
from ..pipeline import Run, Step, drive
from ..tasks import (
    adjacent_env_paths,
    get_task,
    invalidate_dotenv_cache,
    read_dotenv,
    read_toml_config,
    set_env_value,
    write_toml_config,
)
from ..tui import renderer_for
from ..worktree_config import (
    CLONE_IMAGE,
    DEFAULT_ENV,
    DEFAULT_RESET,
    EXAMPLE_BRANCH,
    PLACEHOLDERS,
    SEEDS,
    TemplateError,
    WorktreeConfig,
    classify_env_keys,
    collapse_to_globs,
    dest_volume_name,
    example_values,
    keys_to_reset,
    published_port_keys,
    render_env_templates,
    render_template,
    slugify,
    suggest_copy_entries,
    worktree_dirname,
    worktree_root,
)


class WorktreeError(Exception):
    """Something went wrong that the user has to resolve."""


def ew_command() -> str:
    """
    How to invoke *this* edwh in a subprocess.

    Not a bare `ew`: PATH may point at a different installation (a pipx/uvenv one next to a
    development checkout), and then the worktree would be set up by another version than the one
    the user is running.
    """
    sibling = Path(sys.executable).parent / "ew"
    if sibling.is_file():
        return shlex.quote(str(sibling))

    return f"{shlex.quote(sys.executable)} -m edwh"


# -- git ----------------------------------------------------------------------------------


def _git(c: Context, command: str, cwd: Path | None = None, warn: bool = False) -> str:
    prefix = f"git -C {cwd} " if cwd else "git "
    result = c.run(prefix + command, hide=True, warn=warn)
    return result.stdout.strip() if result else ""


def repo_root(c: Context) -> Path:
    """The main checkout, also when called from inside a linked worktree."""
    common = _git(c, "rev-parse --git-common-dir", warn=True)
    if not common:
        raise WorktreeError("Not inside a git repository.")

    # --git-common-dir gives .../<repo>/.git (or an absolute path to it for a worktree)
    return Path(common).resolve().parent


def worktrees(c: Context) -> list[dict[str, str]]:
    """Every checkout of this repository: the main one first, then linked worktrees."""
    out = _git(c, "worktree list --porcelain", warn=True)

    found: list[dict[str, str]] = []
    for block in out.split("\n\n"):
        entry: dict[str, str] = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            entry[key] = value.strip()
        if "worktree" in entry:
            entry["branch"] = entry.get("branch", "").removeprefix("refs/heads/") or "(detached)"
            found.append(entry)

    return found


def find_worktree(c: Context, branch: str) -> dict[str, str] | None:
    """Locate a worktree by branch name, or by the directory a previous version of edwh gave it."""
    slug = slugify(branch)
    expected = worktree_dirname(repo_root(c).name, branch)

    for entry in worktrees(c):
        # `slug` alone covers worktrees created before directories became `<repo>-<slug>`
        if entry["branch"] == branch or slugify(entry["branch"]) == slug:
            return entry
        if Path(entry["worktree"]).name in (expected, slug):
            return entry

    return None


def branch_exists(c: Context, branch: str) -> bool:
    return bool(_git(c, f"rev-parse --verify --quiet refs/heads/{branch}", warn=True))


def has_unpushed_work(c: Context, path: Path) -> str:
    """Empty string when the worktree is safe to discard, else a description of what would be lost."""
    reasons = []
    if _git(c, "status --porcelain", cwd=path, warn=True):
        reasons.append("uncommitted changes")
    if unpushed := _git(c, "log --oneline @{u}..HEAD", cwd=path, warn=True):
        reasons.append(f"{len(unpushed.splitlines())} unpushed commit(s)")
    return ", ".join(reasons)


# -- config -------------------------------------------------------------------------------


def load_config(toml_path: Path = Path(DEFAULT_TOML_NAME)) -> WorktreeConfig | None:
    """The [worktree] section, or None when the project has not been configured yet."""
    if not toml_path.exists():
        return None

    config = read_toml_config(toml_path)
    if "worktree" not in config:
        return None

    return WorktreeConfig.from_toml(t.cast(dict, config))


def _ask_template(
    key: str,
    current_value: str,
    default: str,
    example: dict[str, str],
    ask: t.Callable[[str], str] = input,
) -> dict[str, str]:
    """
    Ask for one [worktree.env] template, echoing what it would produce.

    Re-asks on a template that cannot expand, so a typo surfaces here instead of halfway through
    creating a worktree.
    """
    context = {**example, "value": current_value}
    print(f"  {key} (now `{current_value}`)")

    while True:
        template = ask(f"   default=`{default}`: ").strip() or default

        if not template:
            return {}

        try:
            rendered = render_template(template, **context)  # type: ignore[arg-type]
        except TemplateError as e:
            cprint(f"   {e}", color="red")
            if template == default:
                # a broken default (from an older .toml) would otherwise be re-offered forever
                default = ""
            continue

        cprint(f"   -> {rendered}", color="green")
        return {key: template}


def _reread_env(path: Path) -> dict[str, str]:
    """
    Read a worktree's .env, ignoring anything cached.

    `ew setup` runs as a subprocess, so the keys it regenerates are invisible to this process's
    read_dotenv cache - which would otherwise still show the stripped-but-not-yet-restored state.
    """
    env_path = (path / DEFAULT_DOTENV_PATH).resolve()
    invalidate_dotenv_cache(env_path)
    return read_dotenv(env_path)


def check_reset_took_effect(source_env: dict[str, str], new_env: dict[str, str], reset: list[str]) -> list[str]:
    """
    Which reset keys came back with the source's value anyway.

    Deleting a key only changes anything when local.setup's default is environment-aware -
    `next_value(...)` or the cwd. Against a constant default like "localhost" the key is simply
    rewritten to the same value, and the two environments quietly share it. Such a key needs a
    [worktree.env] template instead, so say so rather than letting it surface as a collision later.
    """
    return [
        key
        for key in keys_to_reset(source_env, reset)
        if key in new_env and new_env[key] == source_env[key] and source_env[key]
    ]


def _compose_config(c: Context) -> dict[str, t.Any]:
    """`docker compose config` as a dict, or empty when there is no (readable) compose file."""
    result = c.run(f"{DOCKER_COMPOSE} config", hide=True, warn=True, in_stream=False)
    if not result or not result.ok:
        cprint("  (could not read docker compose config; port/hostname analysis skipped)", color="yellow")
        return {}

    return yaml.safe_load(result.stdout) or {}


def _pick_reset_keys(c: Context, env: dict[str, str], compose: dict[str, t.Any], current: WorktreeConfig) -> list[str]:
    """
    Choose the .env keys a worktree must regenerate, from a shortlist rather than all ~80 of them.

    Returns concrete key names, not globs: the caller drops the ones that get a template before
    collapsing what is left.

    Falls back to a plain prompt when there is no .env to reason about yet.
    """
    if not env:
        default_reset = ", ".join(current.reset or DEFAULT_RESET)
        answer = input(f"Which .env keys should be reset (comma separated globs)?\n default=`{default_reset}`: ")
        return [part.strip() for part in (answer.strip() or default_reset).split(",") if part.strip()]

    others = [read_dotenv(path) for path in adjacent_env_paths(c)]
    candidates = classify_env_keys(
        env,
        others,
        published_ports=published_port_keys(compose),
        rewritten=current.env,
    )

    # anything the existing config already resets stays ticked, even if nothing else flags it
    preselected = {item.key for item in candidates if item.suggested} | set(keys_to_reset(env, current.reset))

    if not others:
        cprint(
            "  (no other environments found yet - suggestions are based on docker-compose only. "
            "Re-run this after a second environment exists for better ones.)",
            color="yellow",
        )

    chosen = interactive_selected_checkbox_values(
        {candidate.key: candidate.label for candidate in candidates},
        prompt="Which .env keys must be regenerated per worktree?",
        selected=[key for key in preselected if key in env],
        allow_empty=True,
    )

    return list(chosen or [])


def _as_toml(config: WorktreeConfig) -> str:
    return tomlkit.dumps({"worktree": config.to_toml()})


def save_config(config: WorktreeConfig, toml_path: Path = Path(DEFAULT_TOML_NAME)) -> None:
    toml_path.touch(exist_ok=True)
    existing = read_toml_config(toml_path)
    existing["worktree"] = config.to_toml()
    write_toml_config(toml_path, existing)


def env_vars_in_host_labels(compose: dict[str, t.Any]) -> list[str]:
    """
    Which .env keys the traefik Host() rules depend on.

    Those are the keys that decide whether two environments collide on a hostname, so they are the
    ones worth offering a [worktree.env] template for.
    """
    found: list[str] = []
    for service in (compose.get("services") or {}).values():
        for label, value in (service.get("labels") or {}).items():
            if "Host" not in str(value):
                continue
            for name in re.findall(r"\$\{(\w+)", f"{label}{value}"):
                if name not in found:
                    found.append(name)
    return found


def compose_hosts(c: Context, cwd: Path) -> set[str]:
    """Every traefik hostname an environment claims. Empty set when compose cannot be read."""
    result = c.run(f"cd {cwd} && {DOCKER_COMPOSE} config", hide=True, warn=True)
    if not result or not result.ok:
        return set()

    compose = yaml.safe_load(result.stdout) or {}
    hosts: set[str] = set()
    for service in (compose.get("services") or {}).values():
        hosts |= get_hosts_for_service(service)
    return hosts


# -- tasks --------------------------------------------------------------------------------


@task(
    name="setup",
    # never run as a hook of core `ew setup`: this is an interactive wizard, not project setup
    hookable=False,
    help={"show": "Print the current configuration and exit."},
)
def setup_worktree(c: Context, show: bool = False) -> None:
    """
    Configure how `ew worktree` should build an environment for this project.

    Writes a [worktree] section to .toml, the same per-machine file `ew setup` uses. A project can
    ship defaults for its team by putting the section in default.toml instead.
    """
    root = Path.cwd()
    current = load_config() or WorktreeConfig()

    if show:
        print(_as_toml(current))
        return

    cprint("Configuring `ew worktree` for this project.\n", color="blue")

    # 1. where worktrees live
    default_root = current.root or str(worktree_root())
    answer = input(f"Where should worktrees be created?\n default=`{default_root}`: ").strip()
    current.root = answer or default_root

    # 2. what to copy along
    gitignore = (root / ".gitignore").read_text() if (root / ".gitignore").exists() else ""
    options = suggest_copy_entries(gitignore, root)
    for entry in current.copy:
        if entry not in options:
            options.append(entry)

    if options:
        selected = interactive_selected_checkbox_values(
            options,
            prompt="Which gitignored files/directories should be copied into a new worktree?",
            selected=[entry for entry in current.copy if entry in options]
            or [o for o in options if o in (".env", ".toml")],
        )
        current.copy = list(selected or [])
    else:
        cprint("No gitignored paths found to copy; keeping the defaults.", color="yellow")

    env = read_dotenv(root / DEFAULT_DOTENV_PATH)
    compose = _compose_config(c)

    # 3. which keys are environment-specific at all
    picked = _pick_reset_keys(c, env, compose, current)

    # 4. and how each of them gets its value
    #
    # Deleting a key only helps when local.setup's default is environment-aware (next_value, cwd).
    # For a constant default like "localhost" it regenerates the same value, so those keys need a
    # template instead - which is why every picked key is offered one, not just traefik-label ones.
    candidates = list(dict.fromkeys([*picked, *DEFAULT_ENV, *current.env, *env_vars_in_host_labels(compose)]))

    cprint(
        "\nHow should each of these get its value in a worktree? Give a template, or leave empty "
        "to let local.setup regenerate it.",
        color="blue",
    )
    example = example_values(slugify(repo_root(c).name))
    print(f"  placeholders, shown for the example branch `{EXAMPLE_BRANCH}`:")
    for name in PLACEHOLDERS:
        described = "the current value of that key" if name == "value" else f"`{example[name]}`"
        print(f"    {'{' + name + '}':<10} {described}")
    print()

    rewritten: dict[str, str] = {}
    for key in candidates:
        rewritten |= _ask_template(key, env.get(key, ""), current.env.get(key) or DEFAULT_ENV.get(key) or "", example)

    current.env = rewritten
    # a templated key is written directly, so resetting it as well would be noise
    current.reset = collapse_to_globs([key for key in picked if key not in rewritten], env)
    cprint(f"  reset = {current.reset}", color="grey")

    # 5. database seeding
    available = {seed: seed for seed in SEEDS}
    if not get_task(c, "devdb.recover"):
        available["devdb"] = "devdb (edwh-devdb-plugin is not installed)"
    chosen = interactive_selected_radio_value(
        available,
        prompt="How should a new worktree get its database?",
        selected=current.seed,
    )
    current.seed = str(chosen or current.seed)

    save_config(current)
    cprint(f"\nWritten [worktree] to {DEFAULT_TOML_NAME}.", color="green")
    print(_as_toml(current))


@task(
    name="add",
    default=True,
    aliases=("new", "create"),
    flags={"no_up": ("no-up",), "no_tui": ("no-tui",), "from_ref": ("from", "f")},
    help={
        "branch": "Branch to work on. Created from --from when it does not exist yet.",
        "from_ref": "Base for a new branch (default: HEAD of the current checkout).",
        "seed": f"Override the configured database seeding strategy ({'|'.join(SEEDS)}).",
        "no_up": "Set the environment up but do not start it.",
        "yes": "Do not ask for confirmation (e.g. before pausing services to clone volumes).",
        "no_tui": "Plain line output instead of the live board.",
        "force": "Reuse the target directory even if it already exists.",
    },
)
def add(
    c: Context,
    branch: str,
    from_ref: str = "",
    seed: str = "",
    no_up: bool = False,
    no_tui: bool = False,
    force: bool = False,
    yes: bool = False,
) -> None:
    """
    Create a worktree for `branch` with its own config, ports, hostnames and database.
    """
    source = Path.cwd()
    config = load_config()
    if config is None:
        cprint(f"No [worktree] section in {DEFAULT_TOML_NAME} yet, let's configure one.", color="yellow")
        setup_worktree(c)
        config = load_config()
        if config is None:
            raise WorktreeError("Configuration was not saved, aborting.")

    if seed:
        if seed not in SEEDS:
            raise WorktreeError(f"Unknown seed strategy {seed!r}, choose from {', '.join(SEEDS)}.")
        config.seed = seed

    repo = repo_root(c)
    slug = slugify(branch)
    dst = config.root_path() / worktree_dirname(repo.name, branch)

    if dst.exists() and not force:
        raise WorktreeError(f"{dst} already exists. Use --force to reuse it, or `ew worktree.rm {branch}` first.")

    collisions: dict[str, set[str]] = {}

    async def pipeline(run: Run) -> None:
        await _step_git_add(c, run, repo, branch, from_ref, dst)
        run.check()

        await run.fn("copy config", lambda step: _copy_config(step, source, dst, config.copy))
        await run.fn(
            "rewrite .env",
            lambda step: _rewrite_env(step, source, dst, config, repo=slugify(repo.name), branch=branch, slug=slug),
        )
        run.check()

        await run.fn("check hostnames", lambda step: _check_hosts(step, c, dst, collisions))

        setup_step = await run.sh(
            "setup",
            f"{ew_command()} setup --non-interactive",
            cwd=dst,
            env={"EDWH_NON_INTERACTIVE": "1"},
        )
        _fail_on_broken_hook(setup_step)
        run.check()

        await run.fn("verify .env", lambda step: _verify_reset(step, source, dst, config))

        if no_up:
            run.skip("up", "--no-up")
            run.skip("seed database", "--no-up")
            return

        if collisions and not force:
            # starting it now would give traefik two routers for the same Host() rule, and it
            # picks one at random - which silently breaks the *existing* environment too.
            run.skip("up", f"hostname collision with {', '.join(collisions)}")
            run.skip("seed database", "not started")
            return

        await _step_seed_before_up(c, run, config.seed, source, dst)
        run.check()

        await run.sh("up", f"{ew_command()} up --wait", cwd=dst)
        run.check()

        await _step_seed_after_up(c, run, config.seed, dst)
        await _step_project_hook(c, run, dst)

    if config.seed == "clone" and not no_up and not yes and (paused := running_services_for_clone(c, source)):
        cprint(
            f"Cloning volumes needs a consistent copy, so {', '.join(paused)} will be stopped in "
            f"{source} and started again afterwards.",
            color="yellow",
        )
        if not confirm(colored("Continue? [yN] ", "yellow"), default=False):
            return

    with renderer_for(f"edwh worktree {branch}", tui=not no_tui) as render:
        run = asyncio.run(drive(pipeline, render))

    _report(c, run, branch, dst)


async def _step_git_add(c: Context, run: Run, repo: Path, branch: str, from_ref: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)

    if find_worktree(c, branch):
        run.skip("git worktree add", "worktree already exists")
        return

    if branch_exists(c, branch):
        cmd = f"git -C {repo} worktree add {dst} {branch}"
    else:
        base = from_ref or "HEAD"
        cmd = f"git -C {repo} worktree add -b {branch} {dst} {base}"

    await run.sh("git worktree add", cmd)


def _fail_on_broken_hook(step: Step) -> None:
    """
    Core `setup` swallows a failing project hook into a warning and still exits 0.

    That would leave a worktree whose .env was stripped but never regenerated, which looks like a
    success and breaks much later. Treat it as the failure it is.
    """
    if step.state != "done":
        return

    for line in step.out.splitlines():
        if "Failed running subtask" in line:
            step.state = "failed"
            step.status = line.split("Failed running subtask", 1)[1].strip().removeprefix(":").strip()[:120]
            step.lines.append(line.strip())
            return


def _copy_config(step: Step, source: Path, dst: Path, entries: list[str]) -> None:
    copied, missing = 0, []

    for entry in entries:
        src_path = source / entry.rstrip("/")
        dst_path = dst / entry.rstrip("/")

        if not src_path.exists():
            missing.append(entry)
            continue

        step.report(f"copying {entry}")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        if src_path.is_dir():
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True, symlinks=True)
        else:
            shutil.copy2(src_path, dst_path)
        copied += 1

    status = f"{copied} copied"
    if missing:
        status += f", {len(missing)} missing ({', '.join(missing[:3])})"
    step.report(status)


def _rewrite_env(
    step: Step,
    source: Path,
    dst: Path,
    config: WorktreeConfig,
    *,
    repo: str,
    branch: str,
    slug: str,
) -> None:
    env_path = (dst / DEFAULT_DOTENV_PATH).resolve()
    if not env_path.exists():
        step.report("no .env to rewrite")
        return

    env = read_dotenv(env_path)

    removed = keys_to_reset(env, config.reset)
    for key in removed:
        set_env_value(env_path, key, None)

    rewritten = render_env_templates(env, config.env, repo=repo, branch=branch, slug=slug)
    for key, value in rewritten.items():
        set_env_value(env_path, key, value)

    # values pointing back into the source checkout would silently share state
    leaking = [key for key, value in read_dotenv(env_path).items() if str(source.resolve()) in value]
    if leaking:
        step.lines.append(f"warning: {', '.join(leaking)} still point at {source}")

    step.report(f"-{len(removed)} keys, ={len(rewritten)} rewritten" + (f", {len(leaking)} suspect" if leaking else ""))


def _verify_reset(step: Step, source: Path, dst: Path, config: WorktreeConfig) -> None:
    source_env = read_dotenv((source / DEFAULT_DOTENV_PATH).resolve())
    new_env = _reread_env(dst)

    unchanged = check_reset_took_effect(source_env, new_env, config.reset)
    if not unchanged:
        step.report(f"{len(keys_to_reset(source_env, config.reset))} key(s) regenerated")
        return

    for key in unchanged:
        step.lines.append(
            f"warning: {key} was reset but came back identical to the source (`{source_env[key]}`); "
            f"its default looks constant - give it a [worktree.env] template instead"
        )
    step.report(f"{len(unchanged)} key(s) unchanged after reset")


def _check_hosts(step: Step, c: Context, dst: Path, collisions: dict[str, set[str]]) -> None:
    ours = compose_hosts(c, dst)
    if not ours:
        step.report("no traefik hosts found")
        return

    clashes: dict[str, set[str]] = {}
    for entry in worktrees(c):
        other = Path(entry["worktree"]).resolve()
        if other == dst.resolve():
            continue
        if overlap := ours & compose_hosts(c, other):
            clashes[entry["branch"] or other.name] = overlap

    if not clashes:
        step.report(f"{len(ours)} unique hostname(s)")
        return

    collisions.update(clashes)
    detail = "; ".join(f"{name}: {', '.join(sorted(hosts))}" for name, hosts in clashes.items())
    step.lines.append(f"hostname collision with {detail}")
    step.report(f"COLLISION with {', '.join(clashes)}")


async def _step_seed_before_up(c: Context, run: Run, seed: str, source: Path, dst: Path) -> None:
    """
    Cloning has to happen while the new environment is still down.

    Otherwise `up` lets postgres initialise an empty data directory, and we would be replacing
    files underneath a running server.
    """
    if seed != "clone":
        return

    await run.fn("clone volumes", lambda step: _clone_volumes(step, c, source, dst))


async def _step_seed_after_up(c: Context, run: Run, seed: str, dst: Path) -> None:
    if seed == "fresh":
        run.skip("seed database", "fresh: migrate fills an empty database")
        return

    if seed == "clone":
        return  # already done before `up`

    if not get_task(c, "devdb.recover"):
        run.skip("seed database", "edwh-devdb-plugin is not installed")
        return

    await run.sh("seed database", f"{ew_command()} devdb.recover", cwd=dst)


def _service_of(c: Context, container_id: str) -> str:
    out = c.run(
        f"docker inspect --format '{{{{index .Config.Labels \"com.docker.compose.service\"}}}}' {container_id}",
        hide=True,
        warn=True,
        in_stream=False,
    )
    return out.stdout.strip() if out and out.ok else ""


def _volume_owners(c: Context, path: Path) -> dict[str, list[str]]:
    """Named volume -> the compose services that mount it, for the environment at `path`."""
    ids = c.run(f"cd {path} && {DOCKER_COMPOSE} ps -aq", hide=True, warn=True, in_stream=False)
    if not ids or not ids.ok:
        return {}

    owners: dict[str, list[str]] = {}
    for container_id in ids.stdout.split():
        info = c.run(
            f"docker inspect --format '{{{{range .Mounts}}}}{{{{.Name}}}} {{{{end}}}}' {container_id}",
            hide=True,
            warn=True,
            in_stream=False,
        )
        if not info or not info.ok:
            continue

        service = _service_of(c, container_id)
        for volume in info.stdout.split():
            owners.setdefault(volume, [])
            if service and service not in owners[volume]:
                owners[volume].append(service)

    return owners


def running_services_for_clone(c: Context, source: Path) -> list[str]:
    """
    Which services in the source environment would have to pause for a consistent copy.

    Only the ones actually mounting a volume that travels; the rest of the environment keeps
    serving. Copying a live postgres data directory would give a torn snapshot.
    """
    src_project = source.resolve().name
    running = c.run(
        f"cd {source} && {DOCKER_COMPOSE} ps -q --status running",
        hide=True,
        warn=True,
        in_stream=False,
    )
    if not running or not running.ok or not running.stdout.strip():
        return []

    live = {_service_of(c, container_id) for container_id in running.stdout.split()}

    services: list[str] = []
    for volume, owners in _volume_owners(c, source).items():
        if not dest_volume_name(volume, src_project, "x"):
            continue
        services += [service for service in owners if service in live and service not in services]

    return sorted(services)


def _clone_volumes(step: Step, c: Context, source: Path, dst: Path) -> None:
    src_project = source.resolve().name
    dst_project = dst.resolve().name

    pairs = [
        (volume, target)
        for volume in _volume_owners(c, source)
        if (target := dest_volume_name(volume, src_project, dst_project))
    ]

    if not pairs:
        step.report("no named volumes to clone")
        return

    paused = running_services_for_clone(c, source)
    if paused:
        step.report(f"pausing {', '.join(paused)} in the source")
        c.run(f"cd {source} && {DOCKER_COMPOSE} stop {' '.join(paused)}", hide=True, warn=True)

    try:
        for index, (src_volume, dst_volume) in enumerate(pairs, start=1):
            step.report(f"{index}/{len(pairs)} {src_volume} -> {dst_volume}")
            c.run(f"docker volume create {dst_volume}", hide=True, warn=True)
            copied = c.run(
                f"docker run --rm -v {src_volume}:/from:ro -v {dst_volume}:/to {CLONE_IMAGE} "
                f"sh -c 'cd /from && cp -a . /to/'",
                hide=True,
                warn=True,
            )
            if not copied or not copied.ok:
                raise WorktreeError(f"copying {src_volume} failed: {(copied.stderr if copied else '').strip()[:200]}")
    finally:
        if paused:
            c.run(f"cd {source} && {DOCKER_COMPOSE} start {' '.join(paused)}", hide=True, warn=True)

    step.report(f"{len(pairs)} volume(s) cloned" + (f", restarted {', '.join(paused)}" if paused else ""))


async def _step_project_hook(c: Context, run: Run, dst: Path) -> None:
    """
    Give the project the last word, via a `worktree` task in its own tasks.py.

    Called explicitly rather than through `hookable`: hooks are matched on the task name, which
    here is `add`, and they would be handed this task's arguments.
    """
    if not get_task(c, "local.worktree"):
        return

    await run.sh("local.worktree", f"{ew_command()} local.worktree", cwd=dst)


def _report(c: Context, run: Run, branch: str, dst: Path) -> None:
    print()
    if failures := run.failed:
        for step in failures:
            cprint(f"{step.name} failed: {step.status}", color="red")
            for line in step.lines[-10:]:
                print(f"    {line}")
        cprint(f"\nWorktree left at {dst} so you can inspect it.", color="yellow")
        cprint(f"Remove it with: ew worktree.rm {branch}", color="yellow")
        return

    for step in run.steps:
        for line in step.lines:
            if line.startswith("warning:") or "COLLISION" in line or "collision" in line:
                cprint(f"! {line}", color="yellow")

    env = _reread_env(dst)
    cprint(f"Worktree ready at {dst}", color="green")
    print(f"  PROJECT   {env.get('PROJECT', '?')}")
    if ports := {key: value for key, value in env.items() if key.endswith("_PORT")}:
        print("  ports     " + ", ".join(f"{key}={value}" for key, value in sorted(ports.items())))
    for host in sorted(compose_hosts(c, dst)):
        print(f"  {colored('https://' + host, 'blue')}")
    print(f"\n  cd {dst}")


@task(name="list", aliases=("ls",))
def show_list(c: Context) -> None:
    """Show every worktree of this repository and the state of its environment."""
    import tabulate

    rows = []
    for entry in worktrees(c):
        path = Path(entry["worktree"])
        env = read_dotenv((path / DEFAULT_DOTENV_PATH).resolve())

        # NB: $PROJECT is the project's own naming variable (traefik, container prefixes); compose
        # names the stack after the directory, so ask compose itself instead of guessing either.
        rows.append(
            (
                entry["branch"],
                str(path),
                env.get("PROJECT", "-"),
                _running_containers(c, path) or "-",
                ", ".join(f"{key}={value}" for key, value in sorted(env.items()) if key.endswith("_PORT")) or "-",
            )
        )

    if not rows:
        cprint("No worktrees found.", color="yellow")
        return

    print(tabulate.tabulate(rows, headers=["Branch", "Path", "Project", "Running", "Ports"], tablefmt="pipe"))


def _running_containers(c: Context, path: Path) -> int:
    result = c.run(
        f"cd {path} && {DOCKER_COMPOSE} ps -q --status running",
        hide=True,
        warn=True,
        in_stream=False,
    )
    return len(result.stdout.split()) if result and result.ok else 0


@task(name="path")
def show_path(c: Context, branch: str) -> None:
    """Print the path of a worktree, for `cd $(ew worktree.path my-branch)`."""
    entry = find_worktree(c, branch)
    if not entry:
        raise WorktreeError(f"No worktree for {branch!r}.")
    print(entry["worktree"])


@task(
    name="rm",
    aliases=("remove", "delete"),
    flags={"keep_branch": ("keep-branch",)},
    help={
        "branch": "Branch whose worktree should be removed.",
        "yes": "Do not ask for confirmation, even when work would be lost.",
        "keep_branch": "Keep the git branch, only remove the worktree and its containers.",
    },
)
def rm(c: Context, branch: str, yes: bool = False, keep_branch: bool = False) -> None:
    """
    Tear a worktree down: containers, volumes, directory and (unless --keep-branch) the branch.
    """
    entry = find_worktree(c, branch)
    if not entry:
        raise WorktreeError(f"No worktree for {branch!r}. See `ew worktree.list`.")

    path = Path(entry["worktree"])
    repo = repo_root(c)
    if path.resolve() == repo.resolve():
        raise WorktreeError("Refusing to remove the main checkout.")

    if not yes and (risk := has_unpushed_work(c, path)):
        cprint(f"{path} has {risk}.", color="red")
        try:
            agreed = confirm(colored(f"Really remove {branch}? [yN] ", "red"), default=False)
        except EOFError:
            # no one to ask (piped/CI): never discard work on a guess
            agreed = False
        if not agreed:
            cprint("Aborted. Use --yes to remove it anyway.", color="yellow")
            return

    volumes = _volumes_of(c, path)

    cprint(f"Stopping {branch}...", color="blue")
    c.run(f"cd {path} && {DOCKER_COMPOSE} down -v --remove-orphans", warn=True)

    if volumes:
        cprint(f"Removing {len(volumes)} volume(s)...", color="blue")
        c.run("docker volume rm " + " ".join(volumes), warn=True, hide=True)

    _git(c, f"worktree remove --force {path}", cwd=repo, warn=True)
    _git(c, "worktree prune", cwd=repo, warn=True)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)

    if keep_branch:
        cprint(f"Removed worktree, kept branch {branch}.", color="green")
        return

    deleted = c.run(f"git -C {repo} branch -d {branch}", hide=True, warn=True)
    if deleted and deleted.ok:
        cprint(f"Removed worktree and branch {branch}.", color="green")
    else:
        cprint(f"Removed worktree; branch {branch} kept (it has unmerged work).", color="yellow")


def _volumes_of(c: Context, path: Path) -> list[str]:
    """Named volumes attached to this environment's containers, before it is torn down."""
    ids = c.run(f"cd {path} && {DOCKER_COMPOSE} ps -aq", hide=True, warn=True)
    if not ids or not ids.ok or not ids.stdout.strip():
        return []

    names: list[str] = []
    for container_id in ids.stdout.split():
        info = c.run(
            f"docker inspect --format '{{{{range .Mounts}}}}{{{{.Name}}}} {{{{end}}}}' {container_id}",
            hide=True,
            warn=True,
        )
        if info and info.ok:
            names += [name for name in info.stdout.split() if name and name not in names]

    return names
