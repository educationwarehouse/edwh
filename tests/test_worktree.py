import os
import subprocess
import typing as t
from pathlib import Path

import invoke
import pytest
from ewok import Context

from src.edwh.helpers import viewport
from src.edwh.local_tasks.worktree import _ask_template, check_reset_took_effect
from src.edwh.tasks import (
    _dotenv_settings,
    adjacent_env_paths,
    check_env,
    invalidate_dotenv_cache,
    read_dotenv,
    set_env_value,
)
from src.edwh.worktree_config import (
    DEFAULT_COPY,
    DEFAULT_ENV,
    EXAMPLE_BRANCH,
    SEEDS,
    TemplateError,
    WorktreeConfig,
    classify_env_keys,
    collapse_to_globs,
    dest_volume_name,
    example_values,
    keys_to_reset,
    matches_reset,
    published_port_keys,
    render_env_templates,
    render_template,
    slugify,
    suggest_copy_entries,
    worktree_dirname,
    worktree_root,
)


@pytest.fixture(autouse=True)
def clean_dotenv_cache():
    invalidate_dotenv_cache()
    yield
    invalidate_dotenv_cache()


# -- naming -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("feature/ew-worktree", "feature-ew-worktree"),
        ("feature/EW-Worktree", "feature-ew-worktree"),
        ("release/1.2.0", "release-1-2-0"),
        ("main", "main"),
        ("/weird//branch/", "weird-branch"),
    ],
)
def test_slugify(branch, expected):
    assert slugify(branch) == expected


def test_worktree_root_follows_xdg_cache_home(monkeypatch):
    monkeypatch.delenv("EDWH_WORKTREE_ROOT", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", "/cache")
    assert worktree_root() == Path("/cache/edwh/worktrees")


def test_worktree_root_defaults_under_dot_cache(monkeypatch):
    monkeypatch.delenv("EDWH_WORKTREE_ROOT", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    assert worktree_root() == Path.home() / ".cache" / "edwh" / "worktrees"


def test_edwh_worktree_root_overrides_everything(monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", "/cache")
    monkeypatch.setenv("EDWH_WORKTREE_ROOT", "/elsewhere")
    assert worktree_root() == Path("/elsewhere")


# -- config -------------------------------------------------------------------------------


def test_config_defaults_when_section_is_absent():
    config = WorktreeConfig.from_toml({})
    assert config.copy == DEFAULT_COPY
    assert config.reset == ["*_PORT", "SCHEMA_VERSION", "COMPOSE_PROJECT_NAME"]
    assert config.env == {"PROJECT": "{repo}-{slug}"}
    assert config.seed == "fresh"


def test_config_roundtrips_through_toml():
    original = WorktreeConfig(
        copy=[".env", "shared_keys/"],
        reset=["*_PORT"],
        env={"PROJECT": "{repo}-{slug}", "APPLICATION_NAME": "{slug}-{value}"},
        seed="devdb",
    )
    assert WorktreeConfig.from_toml({"worktree": original.to_toml()}) == original


# -- env rewriting ------------------------------------------------------------------------


def test_matches_reset_is_case_insensitive_and_glob_based():
    assert matches_reset("PGPOOL_PORT", ["*_PORT"])
    assert matches_reset("redis_port", ["*_PORT"])
    assert not matches_reset("PORTAL", ["*_PORT"])
    assert not matches_reset("HOSTINGDOMAIN", ["*_PORT", "SCHEMA_VERSION"])


def test_keys_to_reset_only_selects_matching_keys():
    env = {"PGPOOL_PORT": "5432", "REDIS_PORT": "6379", "PROJECT": "x", "SCHEMA_VERSION": "abc"}
    assert sorted(keys_to_reset(env, ["*_PORT", "SCHEMA_VERSION"])) == ["PGPOOL_PORT", "REDIS_PORT", "SCHEMA_VERSION"]


def test_render_env_templates_expands_all_placeholders():
    env = {"APPLICATION_NAME": "hetnieuwedelen", "PROJECT": "ontwikkelstraat"}
    out = render_env_templates(
        env,
        {"PROJECT": "{repo}-{slug}", "APPLICATION_NAME": "{slug}-{value}", "BRANCH": "{branch}"},
        repo="ontwikkelstraat",
        branch="feature/login",
        slug="feature-login",
    )
    assert out == {
        "PROJECT": "ontwikkelstraat-feature-login",
        "APPLICATION_NAME": "feature-login-hetnieuwedelen",
        "BRANCH": "feature/login",
    }


def test_render_env_templates_resolves_missing_source_value_to_empty():
    out = render_env_templates({}, {"NEW_KEY": "prefix-{value}"}, repo="r", branch="b", slug="s")
    assert out == {"NEW_KEY": "prefix-"}


# -- copy suggestions ---------------------------------------------------------------------


def test_suggest_copy_entries_skips_junk_missing_and_globs(tmp_path: Path):
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / "shared_keys").mkdir()
    (tmp_path / "venv").mkdir()
    (tmp_path / "__pycache__").mkdir()

    gitignore = "\n".join(
        [
            "# a comment",
            ".env",
            "shared_keys/",
            "venv/",
            "__pycache__",
            "*.pyc",
            "/does-not-exist",
            "!.env.example",
        ]
    )

    suggestions = suggest_copy_entries(gitignore, tmp_path)

    assert ".env" in suggestions
    assert "shared_keys/" in suggestions
    assert not [entry for entry in suggestions if "venv" in entry or "pycache" in entry]
    assert not [entry for entry in suggestions if "does-not-exist" in entry]
    assert not [entry for entry in suggestions if "*" in entry]


# -- core fixes ---------------------------------------------------------------------------


def test_check_env_non_interactive_uses_default(tmp_path: Path, monkeypatch):
    """B1: a default must be honoured instead of raising."""
    monkeypatch.setenv("EDWH_NON_INTERACTIVE", "1")
    monkeypatch.delenv("EDWH_FROM_ENV", raising=False)
    env_path = tmp_path / ".env"

    assert check_env("SOME_PORT", "5432", "a port", env_path=env_path) == "5432"
    assert read_dotenv(env_path)["SOME_PORT"] == "5432"


def test_check_env_non_interactive_still_raises_without_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDWH_NON_INTERACTIVE", "1")
    monkeypatch.delenv("EDWH_FROM_ENV", raising=False)

    with pytest.raises(RuntimeError):
        check_env("NO_DEFAULT", None, "nothing", env_path=tmp_path / ".env")


def test_check_env_non_interactive_calls_lazy_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("EDWH_NON_INTERACTIVE", "1")
    monkeypatch.delenv("EDWH_FROM_ENV", raising=False)

    assert check_env("LAZY", lambda: "computed", "lazy", env_path=tmp_path / ".env") == "computed"


def test_set_env_value_invalidates_the_read_cache(tmp_path: Path):
    """B2: read_dotenv used to keep serving a stale dict after a write."""
    env_path = tmp_path / ".env"
    env_path.write_text("PORT=1\n")

    assert read_dotenv(env_path)["PORT"] == "1"
    set_env_value(env_path, "PORT", "2")
    assert read_dotenv(env_path)["PORT"] == "2"


def test_invalidate_dotenv_cache_clears_every_spelling(tmp_path: Path):
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n")

    read_dotenv(env_path)
    assert _dotenv_settings

    invalidate_dotenv_cache(env_path)
    assert str(env_path) not in _dotenv_settings


# -- adjacency (B3) -----------------------------------------------------------------------


def _ctx() -> Context:
    """A bare local context, the same cast `TomlConfig.load` uses."""
    return t.cast(Context, invoke.Context())


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


@pytest.fixture
def repo_with_worktree(tmp_path: Path):
    """A main checkout with one linked worktree living somewhere else entirely."""
    main = tmp_path / "projects" / "myrepo"
    main.mkdir(parents=True)
    _git(main, "init", "-q", "-b", "main")
    (main / "README").write_text("x")
    _git(main, "add", ".")
    _git(main, "commit", "-qm", "init")
    (main / ".env").write_text("PGPOOL_PORT=5432\n")

    linked = tmp_path / "data" / "worktrees" / "myrepo" / "feature-x"
    linked.parent.mkdir(parents=True)
    _git(main, "worktree", "add", "-q", "-b", "feature-x", str(linked))
    (linked / ".env").write_text("PGPOOL_PORT=5433\n")

    sibling = main.parent / "other-project"
    sibling.mkdir()
    (sibling / ".env").write_text("PGPOOL_PORT=5500\n")

    return main, linked, sibling


def test_adjacent_env_paths_finds_worktree_from_main(repo_with_worktree, monkeypatch):
    main, linked, sibling = repo_with_worktree
    monkeypatch.chdir(main)

    found = {path.resolve() for path in adjacent_env_paths(_ctx())}

    assert (linked / ".env").resolve() in found, "a worktree outside the sibling layout must be seen"
    assert (sibling / ".env").resolve() in found, "the historic ../*/.env glob must keep working"


def test_adjacent_env_paths_finds_main_from_worktree(repo_with_worktree, monkeypatch):
    main, linked, _ = repo_with_worktree
    monkeypatch.chdir(linked)

    found = {path.resolve() for path in adjacent_env_paths(_ctx())}

    assert (main / ".env").resolve() in found, "a worktree must see the main checkout's ports"


def test_adjacent_env_paths_deduplicates(repo_with_worktree, monkeypatch):
    main, _, _ = repo_with_worktree
    monkeypatch.chdir(main)

    resolved = [path.resolve() for path in adjacent_env_paths(_ctx())]

    assert len(resolved) == len(set(resolved))


def test_adjacent_env_paths_outside_git_falls_back_to_siblings(tmp_path: Path, monkeypatch):
    project = tmp_path / "a"
    project.mkdir()
    other = tmp_path / "b"
    other.mkdir()
    (other / ".env").write_text("X=1\n")
    monkeypatch.chdir(project)

    found = {path.resolve() for path in adjacent_env_paths(_ctx())}
    assert (other / ".env").resolve() in found


# -- env key detection --------------------------------------------------------------------


def test_published_port_keys_only_reports_the_host_side():
    compose = {
        "services": {
            "web": {"ports": ["${WEB_PORT}:80"]},
            "db": {"ports": [{"published": "${PG_PORT}", "target": 5432}]},
            "fixed": {"ports": ["9000:9000"]},
            "internal": {"ports": ["80"]},
            "nothing": {},
        }
    }

    assert published_port_keys(compose) == {"WEB_PORT", "PG_PORT"}


def test_published_port_keys_ignores_the_container_side():
    assert published_port_keys({"services": {"a": {"ports": ["8080:${CONTAINER_PORT}"]}}}) == set()


def test_classify_flags_published_ports_even_without_other_envs():
    env = {"WEB_PORT": "8080", "API_KEY": "sk-1"}

    by_key = {c.key: c for c in classify_env_keys(env, others=[], published_ports={"WEB_PORT"})}

    assert by_key["WEB_PORT"].suggested
    assert "published port" in by_key["WEB_PORT"].reasons
    assert not by_key["API_KEY"].suggested


def test_classify_uses_differences_between_existing_environments():
    env = {"PGPOOL_PORT": "5432", "SMTP_PASSWORD": "hunter2", "PROJECT": "a"}
    others = [
        {"PGPOOL_PORT": "5433", "SMTP_PASSWORD": "hunter2", "PROJECT": "b"},
        {"PGPOOL_PORT": "5434", "SMTP_PASSWORD": "hunter2", "PROJECT": "c"},
    ]

    by_key = {c.key: c for c in classify_env_keys(env, others)}

    assert by_key["PGPOOL_PORT"].suggested, "a value that differs per environment must be reset"
    assert by_key["PROJECT"].suggested
    assert not by_key["SMTP_PASSWORD"].suggested, "identical everywhere means shared config"
    assert "identical in 3 envs" in by_key["SMTP_PASSWORD"].reasons


def test_classify_never_suggests_a_key_that_worktree_env_rewrites():
    env = {"PROJECT": "a"}
    others = [{"PROJECT": "b"}]

    by_key = {c.key: c for c in classify_env_keys(env, others, rewritten={"PROJECT"})}

    assert not by_key["PROJECT"].suggested, "rewriting and resetting the same key would conflict"
    assert by_key["PROJECT"].reasons == ["handled by [worktree.env]"]


def test_classify_puts_suggested_candidates_first():
    env = {"AAA_SHARED": "x", "ZZZ_PORT": "1"}

    order = [c.key for c in classify_env_keys(env, others=[], published_ports={"ZZZ_PORT"})]

    assert order == ["ZZZ_PORT", "AAA_SHARED"]


# -- glob collapsing ----------------------------------------------------------------------


def test_collapse_uses_a_glob_only_when_the_whole_family_is_selected():
    all_keys = ["PGPOOL_PORT", "REDIS_PORT", "PGSTATS_PORT", "SCHEMA_VERSION", "API_KEY"]

    assert collapse_to_globs(["PGPOOL_PORT", "REDIS_PORT", "PGSTATS_PORT", "SCHEMA_VERSION"], all_keys) == [
        "*_PORT",
        "SCHEMA_VERSION",
    ]


def test_collapse_keeps_literals_on_a_partial_family():
    all_keys = ["PGPOOL_PORT", "REDIS_PORT", "SMTP_PORT"]

    assert collapse_to_globs(["PGPOOL_PORT", "REDIS_PORT"], all_keys) == ["PGPOOL_PORT", "REDIS_PORT"]


def test_collapse_does_not_glob_a_family_of_one():
    assert collapse_to_globs(["WEB_PORT"], ["WEB_PORT", "API_KEY"]) == ["WEB_PORT"]


def test_collapse_roundtrips_through_keys_to_reset():
    all_keys = ["PGPOOL_PORT", "REDIS_PORT", "SCHEMA_VERSION", "API_KEY"]
    picked = ["PGPOOL_PORT", "REDIS_PORT", "SCHEMA_VERSION"]

    globs = collapse_to_globs(picked, all_keys)

    assert sorted(keys_to_reset(dict.fromkeys(all_keys, ""), globs)) == sorted(picked)


def test_collapse_of_nothing_is_nothing():
    assert collapse_to_globs([], ["A_PORT"]) == []


# -- viewport -----------------------------------------------------------------------------


def test_viewport_shows_everything_when_it_fits():
    assert viewport(count=5, cursor=0, height=10) == (0, 5)


def test_viewport_keeps_the_cursor_inside_the_window():
    for cursor in range(80):
        start, stop = viewport(count=80, cursor=cursor, height=10)
        assert start <= cursor < stop
        assert stop - start == 10


def test_viewport_clamps_at_both_ends():
    assert viewport(count=80, cursor=0, height=10) == (0, 10)
    assert viewport(count=80, cursor=79, height=10) == (70, 80)


# -- template rendering and validation ------------------------------------------------------


def test_render_template_expands_every_placeholder():
    out = render_template("{repo}/{branch}/{slug}/{value}", value="v", repo="r", branch="f/b", slug="f-b")
    assert out == "r/f/b/f-b/v"


def test_render_template_rejects_an_unknown_placeholder_with_a_usable_message():
    with pytest.raises(TemplateError) as excinfo:
        render_template("{naam}-{value}", value="v", repo="r", branch="b", slug="s")

    message = str(excinfo.value)
    assert "{naam}" in message, "name the offending placeholder"
    assert "{slug}" in message, "list the valid ones"


def test_render_template_rejects_a_malformed_template():
    with pytest.raises(TemplateError):
        render_template("{value", value="v", repo="r", branch="b", slug="s")


def test_render_template_allows_an_escaped_brace():
    assert render_template("{{literal}}-{slug}", value="", repo="r", branch="b", slug="s") == "{literal}-s"


def test_render_env_templates_surfaces_a_bad_template_as_template_error():
    """A typo must not reach worktree creation as a bare KeyError."""
    with pytest.raises(TemplateError):
        render_env_templates({}, {"K": "{nope}"}, repo="r", branch="b", slug="s")


def test_example_values_demonstrates_slugification():
    example = example_values("ontwikkelstraat")

    assert example["repo"] == "ontwikkelstraat"
    assert example["branch"] == EXAMPLE_BRANCH
    assert example["slug"] == slugify(EXAMPLE_BRANCH)
    assert example["slug"] != example["branch"], "the example must show what slugify does"


def test_example_values_takes_the_real_current_value():
    assert example_values("r", current_value="localhost")["value"] == "localhost"


def test_ask_template_does_not_loop_forever_on_a_broken_default():
    """
    A bad template in an existing .toml is re-offered as the default. Accepting it with Enter must
    not re-offer it forever - the only escape would be Ctrl-C, losing every earlier answer.
    """
    answers = iter(["", "", ""])
    result = _ask_template(
        "PROJECT",
        current_value="demo",
        default="{oud}-{slug}",
        example=example_values("repo"),
        ask=lambda _: next(answers),
    )

    assert result == {}, "after rejecting the broken default, Enter means skip"


# -- volume cloning -----------------------------------------------------------------------


def test_dest_volume_name_swaps_the_compose_project_prefix():
    assert dest_volume_name("demo_pgdata", "demo", "feature-login") == "feature-login_pgdata"


def test_dest_volume_name_keeps_the_rest_of_the_name_intact():
    assert dest_volume_name("demo_shared_uploads", "demo", "wt") == "wt_shared_uploads"


def test_dest_volume_name_skips_anonymous_and_external_volumes():
    """No project prefix means anonymous (recreated empty) or external (shared on purpose)."""
    assert dest_volume_name("a1b2c3d4e5f6", "demo", "wt") is None
    assert dest_volume_name("shared_broker", "demo", "wt") is None


def test_dest_volume_name_does_not_match_a_project_that_is_only_a_prefix():
    assert dest_volume_name("demo2_pgdata", "demo", "wt") is None


def test_clone_is_an_offered_seed_and_hook_is_gone():
    assert "clone" in SEEDS
    assert "hook" not in SEEDS
    assert sorted(SEEDS) == ["clone", "devdb", "fresh"]


# -- directory naming ---------------------------------------------------------------------


def test_worktree_dirname_is_flat_and_names_the_repo():
    """A prompt showing only the basename should still say which project you are in."""
    assert worktree_dirname("Appelsap", "test-worktrees") == "appelsap-test-worktrees"


def test_worktree_dirname_matches_the_default_project_template():
    """
    Compose derives its project name from this directory and lowercases it, so the directory and
    the default PROJECT template must produce the same string.
    """
    repo, branch = "Appelsap", "feature/login"
    directory = worktree_dirname(repo, branch)
    project = render_template(DEFAULT_ENV["PROJECT"], value="", repo=slugify(repo), branch=branch, slug=slugify(branch))

    assert directory == project == "appelsap-feature-login"


def test_compose_project_name_is_reset_by_default():
    """It outranks the directory name, so a copied one would fuse the worktree with its source."""
    assert "COMPOSE_PROJECT_NAME" in WorktreeConfig().reset


# -- reset verification -------------------------------------------------------------------


def test_check_reset_took_effect_flags_a_constant_default():
    source = {"HOSTINGDOMAIN": "localhost", "PGPOOL_PORT": "5432"}
    new = {"HOSTINGDOMAIN": "localhost", "PGPOOL_PORT": "5433"}

    assert check_reset_took_effect(source, new, ["*_PORT", "HOSTINGDOMAIN"]) == ["HOSTINGDOMAIN"]


def test_check_reset_took_effect_is_quiet_when_everything_regenerated():
    source = {"PGPOOL_PORT": "5432"}
    new = {"PGPOOL_PORT": "5433"}

    assert check_reset_took_effect(source, new, ["*_PORT"]) == []


def test_check_reset_took_effect_ignores_keys_that_stayed_absent():
    """local.setup may legitimately not re-add a key; that is not the failure we are hunting."""
    assert check_reset_took_effect({"GONE": "x"}, {}, ["GONE"]) == []


def test_check_reset_took_effect_ignores_empty_values():
    """An empty value matching an empty value tells us nothing."""
    assert check_reset_took_effect({"BLANK": ""}, {"BLANK": ""}, ["BLANK"]) == []
