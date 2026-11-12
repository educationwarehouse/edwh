"""Build the edwh homepage into a single self-contained HTML file.

Inlines the fonts, doodles and logo from `assets/` and renders the latest
releases from the repository's CHANGELOG.md. Standard library only.

usage: python site/build.py [--out site/dist/index.html]
"""

import argparse
import base64
import datetime as dt
import html
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent
ASSETS = SITE / "assets"
CHANGELOG = SITE.parent / "CHANGELOG.md"

RELEASE_RE = re.compile(r"^## v?(\S+) \((\d{4}-\d{2}-\d{2})\)")


def b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def b64_text(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def inline_md(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def parse_changelog(path: Path, limit: int) -> list[dict]:
    releases: list[dict] = []
    section = None
    for line in path.read_text().splitlines():
        if match := RELEASE_RE.match(line):
            if len(releases) == limit:
                break
            releases.append({"version": match.group(1), "date": match.group(2), "items": []})
            section = None
        elif releases and (match := re.match(r"^### (.+)", line)):
            section = match.group(1).strip()
        elif releases and section and (match := re.match(r"^\* (.+)", line)):
            releases[-1]["items"].append((section, match.group(1)))
    return releases


def render_changelog(releases: list[dict]) -> str:
    items = []
    for release in releases:
        if not release["items"]:
            continue
        kind, message = release["items"][0]
        lowered = kind.lower()
        cls = "feature" if lowered.startswith("feat") else "fix" if lowered.startswith("fix") else "other"
        label = {"feature": "Feature", "fix": "Fix"}.get(cls, kind)
        day = dt.date.fromisoformat(release["date"])
        date = f"{day.day} {day:%b %Y}"
        items.append(
            f'<li><span class="v">v{html.escape(release["version"])}</span>'
            f'<span class="date">{date}</span><br>'
            f'<span class="tag {cls}">{html.escape(label)}</span><p>{inline_md(message)}</p></li>'
        )
    return '<ol class="cl">' + "".join(items) + "</ol>"


def build() -> str:
    page = (SITE / "template.html").read_text()

    for weight in (300, 400, 600, 700, 800, 900):
        page = page.replace(f"{{{{F{weight}}}}}", b64(ASSETS / "fonts" / f"figtree-{weight}.woff2"))

    icon = (ASSETS / "icon-mark.svg").read_text()
    page = page.replace("{{ICON_MARK_DARK}}", b64_text(re.sub("#25303d", "#ffffff", icon, flags=re.I)))
    page = page.replace("{{ICON_MARK}}", b64_text(icon))

    page = re.sub(
        r"\{\{D(\w+)\}\}",
        lambda m: "data:image/png;base64," + b64(ASSETS / "doodles" / f"{m.group(1)}.png"),
        page,
    )

    releases = parse_changelog(CHANGELOG, limit=4)
    page = page.replace("{{VERSION}}", releases[0]["version"] if releases else "")
    page = page.replace("{{CHANGELOG}}", render_changelog(releases))

    if leftover := re.findall(r"\{\{\w+\}\}", page):
        raise SystemExit(f"unresolved placeholders: {sorted(set(leftover))}")
    return page


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=SITE / "dist" / "index.html")
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build())
    print(f"wrote {args.out} ({args.out.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
