"""Serve the edwh homepage, keeping its "What's new" strip in sync with the published changelog.

The page itself is built once at startup. The changelog is fetched by this server (never by
visitors' browsers), cached for CHANGELOG_TTL seconds and refreshed in the background, so
requests never wait on GitHub. Until a fetch succeeds, and whenever one fails, the last good
changelog is served; at startup that is the CHANGELOG.md baked into the image.

Standard library only. Meant to run behind Traefik, which terminates TLS.

env:
    CHANGELOG_URL  where to fetch CHANGELOG.md (default: edwh's main branch on GitHub)
    CHANGELOG_TTL  seconds before the cached changelog is refreshed (default: 3600)
    PORT           port to listen on (default: 8000)
"""

import gzip
import hashlib
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import homepage

DEFAULT_CHANGELOG_URL = "https://raw.githubusercontent.com/educationwarehouse/edwh/main/CHANGELOG.md"
RETRY_AFTER_FAILURE = 60  # seconds; don't hammer the source while it's down

log = logging.getLogger("edwh-site")


@dataclass(frozen=True)
class Rendered:
    body: bytes
    gzipped: bytes
    etag: str

    @classmethod
    def from_html(cls, page: str) -> "Rendered":
        body = page.encode()
        return cls(body=body, gzipped=gzip.compress(body), etag=f'"{hashlib.sha256(body).hexdigest()[:20]}"')


class Page:
    """The rendered homepage plus the changelog cache behind it."""

    def __init__(self, shell: str, changelog: str, url: str, ttl: float, timeout: float = 5.0) -> None:
        self.shell = shell
        self.url = url
        self.ttl = ttl
        self.timeout = timeout

        self.changelog = changelog
        self.rendered = Rendered.from_html(homepage.fill(shell, changelog))
        self._source_etag: str | None = None
        self._next_check = 0.0  # time.monotonic(); 0 means "refresh on first use"
        self._refreshing = threading.Lock()

    def current(self) -> Rendered:
        """The page to serve now; kicks off a background refresh when the cache is stale."""
        if time.monotonic() >= self._next_check:
            self.refresh_in_background()
        return self.rendered

    def refresh_in_background(self) -> None:
        # non-blocking acquire: if a refresh is already running, this request just serves the cache
        if self._refreshing.acquire(blocking=False):
            threading.Thread(target=self._refresh_and_release, daemon=True).start()

    def _refresh_and_release(self) -> None:
        try:
            self.refresh()
        finally:
            self._refreshing.release()

    def refresh(self) -> bool:
        """Fetch the changelog and re-render if it changed. Returns whether the page changed."""
        try:
            text, etag = self._fetch()
            if text is None or text == self.changelog:
                changed = False
            else:
                if not homepage.parse_changelog(text):
                    raise ValueError("no releases found in fetched changelog")
                self.rendered = Rendered.from_html(homepage.fill(self.shell, text))
                self.changelog = text
                changed = True
                log.info("changelog updated from %s", self.url)
            self._source_etag = etag or self._source_etag
            self._next_check = time.monotonic() + self.ttl
            return changed
        except Exception as exc:  # keep serving the last good page whatever goes wrong
            log.warning("changelog refresh from %s failed, keeping cached version: %s", self.url, exc)
            self._next_check = time.monotonic() + min(self.ttl, RETRY_AFTER_FAILURE)
            return False

    def _fetch(self) -> tuple[str | None, str | None]:
        """(text, etag); text is None when the source says it's unchanged (304)."""
        request = urllib.request.Request(self.url, headers={"User-Agent": "edwh-site"})
        if self._source_etag:
            request.add_header("If-None-Match", self._source_etag)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read().decode(), response.headers.get("ETag")
        except urllib.error.HTTPError as exc:
            if exc.code == HTTPStatus.NOT_MODIFIED:
                return None, None
            raise


def make_handler(page: Page) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "edwh-site"
        sys_version = ""

        def do_GET(self) -> None:
            self._respond(send_body=True)

        def do_HEAD(self) -> None:
            self._respond(send_body=False)

        def _respond(self, send_body: bool) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                self._send(HTTPStatus.OK, b"ok\n", "text/plain; charset=utf-8", send_body)
            elif path in ("/", "/index.html"):
                self._send_page(page.current(), send_body)
            else:
                self._send(HTTPStatus.NOT_FOUND, b"not found\n", "text/plain; charset=utf-8", send_body)

        def _send_page(self, rendered: Rendered, send_body: bool) -> None:
            if self.headers.get("If-None-Match") == rendered.etag:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("ETag", rendered.etag)
                self.end_headers()
                return

            use_gzip = "gzip" in self.headers.get("Accept-Encoding", "")
            body = rendered.gzipped if use_gzip else rendered.body
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")  # always revalidate; the ETag makes that cheap
            self.send_header("ETag", rendered.etag)
            self.send_header("Vary", "Accept-Encoding")
            if use_gzip:
                self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def _send(self, status: HTTPStatus, body: bytes, content_type: str, send_body: bool) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if send_body:
                self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - signature from stdlib
            if self.path != "/healthz":  # the healthcheck would otherwise flood the log
                log.info("%s %s", self.address_string(), format % args)

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    page = Page(
        shell=homepage.build_shell(),
        changelog=homepage.CHANGELOG.read_text(),  # baked into the image; used until the first fetch
        url=os.environ.get("CHANGELOG_URL", DEFAULT_CHANGELOG_URL),
        ttl=float(os.environ.get("CHANGELOG_TTL", "3600")),
    )
    page.refresh_in_background()

    port = int(os.environ.get("PORT", "8000"))
    # all interfaces: runs in a container, reachable only through Traefik on the broker network
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(page))
    log.info("serving on :%d, changelog from %s (ttl %ss)", port, page.url, page.ttl)
    server.serve_forever()


if __name__ == "__main__":
    main()
