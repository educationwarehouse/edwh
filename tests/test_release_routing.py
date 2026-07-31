# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT
"""
How plugin.release and plugin.bump choose, and refuse, a release backend.
"""

from contextlib import chdir

import invoke
import pytest

from src.edwh.local_tasks import plugin

VOMMIT = """[project]
name = "demo"
version = "1.0.0"

[tool.vommit]
prerelease_token = "beta"
"""

BARE = """[project]
name = "demo"
version = "1.0.0"
"""


@pytest.fixture
def project(tmp_path):
    """Build a throwaway project to run a task inside."""

    def make(content: str):
        (tmp_path / "pyproject.toml").write_text(content)
        return tmp_path

    return make


@pytest.fixture
def no_vommit(monkeypatch):
    """An environment where the optional `vommit` extra is not installed."""
    monkeypatch.setattr(plugin, "vommit_tasks", lambda: None)


@pytest.fixture
def refuses_install(monkeypatch):
    """Decline the install offer, and record that it was made."""
    offered = []

    def decline(prompt, **_kwargs):
        offered.append(prompt)
        return False

    monkeypatch.setattr(plugin, "confirm", decline)
    return offered


@pytest.fixture
def no_psr(monkeypatch):
    """Make any attempt to reach python-semantic-release loud instead of silent."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("reached the python-semantic-release path")

    monkeypatch.setattr(plugin, "_psr_bump", forbidden)
    monkeypatch.setattr(plugin, "require_semantic_release", forbidden)
    monkeypatch.setattr(plugin, "_semantic_release_publish", forbidden)


@pytest.mark.usefixtures("no_vommit")
def test_configured_for_vommit_but_not_installed_offers_the_install(project, refuses_install):
    """
    vommit's config outlives its install -- a migrated project cloned onto a
    second machine has [tool.vommit] and no vommit. That has to reach the
    install offer, not an assertion.
    """
    with chdir(project(VOMMIT)):
        assert plugin._resolve_backend(invoke.Context()) is None

    assert refuses_install, "no install was offered"
    assert "vommit is not installed" in refuses_install[0]


@pytest.mark.usefixtures("no_vommit", "refuses_install", "no_psr")
def test_declining_that_install_does_not_release(project):
    """Refusing the install must stop, not fall back to the deprecated path."""
    with chdir(project(VOMMIT)):
        plugin.release(invoke.Context(), noop=True, pull=False)
        # ewok hands back its own empty result rather than None, so this asserts
        # no version came out -- and `no_psr` raises if psr was reached at all
        assert not plugin.bump(invoke.Context(), noop=True)


def test_accepting_that_install_proceeds(project, monkeypatch):
    """Once vommit is importable, the backend resolves to it."""
    installed = []
    monkeypatch.setattr(plugin, "confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(plugin, "pip_install", lambda _ctx, *specs, **_kwargs: installed.extend(specs))
    # absent until the install "runs", importable afterwards
    monkeypatch.setattr(plugin, "vommit_tasks", lambda: object() if installed else None)

    with chdir(project(VOMMIT)):
        assert plugin._resolve_backend(invoke.Context()) == "vommit"

    assert installed and installed[0].startswith("vommit")


@pytest.mark.usefixtures("no_psr")
def test_bump_without_any_backend_does_not_reach_psr(project, monkeypatch):
    """
    `release` already refused this; `bump` used to install psr and run it
    against a project that has no psr config.
    """
    monkeypatch.setattr(plugin, "_can_ask", lambda: False)

    with chdir(project(BARE)):
        assert not plugin.bump(invoke.Context(), noop=True)


def test_install_specifier_carries_the_declared_bound():
    """
    The install prompt must not be able to pull a vommit edwh does not support.
    """
    specifier = plugin.vommit_specifier()

    assert specifier, "no version bound at all"
    assert "<1" in specifier.replace(" ", "")
    assert plugin._vommit_spec().startswith("vommit")
    assert plugin._vommit_spec().endswith(specifier)


@pytest.mark.usefixtures("no_vommit", "refuses_install")
def test_require_vommit_task_keeps_its_result_to_itself(project):
    """
    ewok writes a task's return value into the shared ctx["result"], which the
    enclosing task then returns as its own. `ensure_vommit` is a plain function
    for that reason; the task wrapper must not reintroduce the leak.
    """
    ctx = invoke.Context()

    with chdir(project(VOMMIT)):
        plugin.require_vommit(ctx)

    assert not ctx["result"], f"leaked {ctx['result']!r} into the shared result"
