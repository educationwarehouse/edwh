"""The homepage in site/: changelog rendering, the cached refresh, and the HTTP server."""

import gzip
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import homepage
import pytest
from homepage_server import Page, make_handler

SHELL = "<footer>v{{VERSION}}</footer>{{CHANGELOG}}"


def changelog(*versions: str) -> str:
    entries = "".join(
        f"## v{version} (2026-11-12)\n\n### Fix\n* **site:** release {version}\n\n" for version in versions
    )
    return f"# Changelog\n\n<!--next-version-placeholder-->\n\n{entries}"


def source(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(text)
    return path


def test_fill_renders_newest_releases_and_version() -> None:
    page = homepage.fill(SHELL, changelog("1.2.0", "1.1.0"))

    assert "<footer>v1.2.0</footer>" in page
    assert page.index("v1.2.0") < page.index("v1.1.0")
    assert "<b>site:</b> release 1.2.0" in page


def test_parse_changelog_limits_releases() -> None:
    releases = homepage.parse_changelog(changelog("5", "4", "3", "2", "1"), limit=2)

    assert [release["version"] for release in releases] == ["5", "4"]


def test_refresh_picks_up_a_new_release(tmp_path: Path) -> None:
    path = source(tmp_path, changelog("1.0.0"))
    page = Page(SHELL, changelog("1.0.0"), url=path.as_uri(), ttl=600)

    assert page.refresh() is False  # same as the baked-in changelog

    path.write_text(changelog("1.1.0", "1.0.0"))
    assert page.refresh() is True
    assert b"<footer>v1.1.0</footer>" in page.rendered.body


def test_refresh_keeps_last_good_page_when_source_is_unreachable(tmp_path: Path) -> None:
    page = Page(SHELL, changelog("1.0.0"), url=(tmp_path / "missing.md").as_uri(), ttl=600)
    before = page.rendered

    assert page.refresh() is False
    assert page.rendered is before


def test_refresh_ignores_a_changelog_without_releases(tmp_path: Path) -> None:
    path = source(tmp_path, "<html>rate limited</html>")
    page = Page(SHELL, changelog("1.0.0"), url=path.as_uri(), ttl=600)

    assert page.refresh() is False
    assert b"<footer>v1.0.0</footer>" in page.rendered.body


@pytest.fixture
def base_url(tmp_path: Path) -> Iterator[str]:
    page = Page(SHELL, changelog("1.0.0"), url=source(tmp_path, changelog("1.0.0")).as_uri(), ttl=600)
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(page))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def test_server_serves_gzipped_page_with_etag(base_url: str) -> None:
    request = urllib.request.Request(f"{base_url}/", headers={"Accept-Encoding": "gzip"})
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.headers["Content-Encoding"] == "gzip"
        assert response.headers["Cache-Control"] == "no-cache"
        etag = response.headers["ETag"]
        body = gzip.decompress(response.read())

    assert b"<footer>v1.0.0</footer>" in body

    revalidate = urllib.request.Request(f"{base_url}/", headers={"If-None-Match": etag})
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(revalidate, timeout=5)
    assert exc.value.code == 304


def test_server_health_and_unknown_paths(base_url: str) -> None:
    with urllib.request.urlopen(f"{base_url}/healthz", timeout=5) as response:
        assert response.read() == b"ok\n"

    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/nope", timeout=5)
    assert exc.value.code == 404
