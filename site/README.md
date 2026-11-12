# edwh homepage

A single-page site for edwh, built into one self-contained `index.html`
(fonts, doodles and logo are inlined). The "What's new" strip and the version
in the footer come from the repository's `CHANGELOG.md` at build time.

## Build locally

```console
python site/build.py            # writes site/dist/index.html (or: cd site && ew local.build)
```

Standard library only; open the result directly in a browser.

## Deploy

Served by nginx behind the shared Traefik on the external `broker` network:

```console
cd site
ew setup        # asks for EDWH_SITE_DOMAIN (default edwh.localhost)
ew up
```

Plain Compose works too: `cp site/.env.example site/.env`, then
`docker compose -f site/docker-compose.yml up -d --build`.

Rebuild after a release to pick up the new changelog entries.

The hostname variable is `EDWH_SITE_DOMAIN`, not `HOSTINGDOMAIN`: Compose lets exported
shell variables override `.env`, so a `HOSTINGDOMAIN` exported for another project would
otherwise route this site onto that project's hostname.

## Assets

- `assets/fonts/`: [Figtree](https://github.com/erikdkennedy/figtree), SIL Open Font License (`OFL.txt`).
  Stand-in for Proxima Nova, which is commercially licensed and can't be published here.
- `assets/doodles/`, `assets/icon-mark.svg`: Education Warehouse brand assets from the
  design system; only the ones used on the page.
