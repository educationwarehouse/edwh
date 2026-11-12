# edwh homepage

A single-page site for edwh: one self-contained HTML page (fonts, doodles and logo are
inlined) whose "What's new" strip and footer version come from `CHANGELOG.md`.

## How it stays up to date

`homepage_server.py` builds the page once at startup, then keeps the changelog part fresh:

- it fetches `CHANGELOG.md` from edwh's `main` branch on GitHub (`CHANGELOG_URL`),
  caches it for `CHANGELOG_TTL` seconds (default 3600, an hour) and refreshes in the background,
  so a request never waits on GitHub and visitors' browsers never contact it;
- if a fetch fails or returns something without releases, it keeps serving the last good
  version; until the first fetch succeeds that is the `CHANGELOG.md` baked into the image.

So after `edwh plugin.release` the site shows the new release within about an hour, no
redeploy needed. Redeploy only when the page itself (`template.html`, `assets/`) changes.

## Run it

```console
cd site
ew setup        # asks for EDWH_SITE_DOMAIN (default edwh.localhost)
ew up
```

Plain Compose works too: `cp site/.env.example site/.env`, then
`docker compose -f site/docker-compose.yml up -d --build`.

The hostname variable is `EDWH_SITE_DOMAIN`, not `HOSTINGDOMAIN`: Compose lets exported
shell variables override `.env`, so a `HOSTINGDOMAIN` exported for another project would
otherwise route this site onto that project's hostname.

## Preview without Docker

```console
python site/homepage.py         # static build to site/dist/index.html (or: cd site && ew local.build)
python site/homepage_server.py  # the real server on :8000
```

Both are standard library only.

## Assets

- `assets/fonts/`: [Figtree](https://github.com/erikdkennedy/figtree), SIL Open Font License (`OFL.txt`).
  Stand-in for Proxima Nova, which is commercially licensed and can't be published here.
- `assets/doodles/`, `assets/icon-mark.svg`: Education Warehouse brand assets from the
  design system; only the ones used on the page.
