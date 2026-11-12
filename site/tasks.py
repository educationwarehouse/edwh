"""edwh tasks for the homepage in site/: `ew setup`, `ew up`, `ew local.build`."""

import sys
from pathlib import Path

from invoke import Context

import edwh
from edwh import improved_task as task

SITE = Path(__file__).resolve().parent


@task()
def setup(_: Context) -> None:
    """Ask for the site's hostname; runs after the global `ew setup`."""
    edwh.check_env(
        key="EDWH_SITE_DOMAIN",
        default="edwh.localhost",
        comment="Hostname Traefik should route to the edwh homepage (not shared with another project)",
    )
    edwh.check_env(
        key="CERTRESOLVER",
        default="default",
        comment="Traefik certificate resolver",
    )


@task()
def build(c: Context) -> None:
    """Build site/dist/index.html without Docker, for a quick local preview."""
    c.run(f"{sys.executable} {SITE / 'build.py'}")
