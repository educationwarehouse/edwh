# Build context is the repository root (needs CHANGELOG.md), see docker-compose.yml.
FROM python:3.13-alpine AS build
WORKDIR /src
COPY CHANGELOG.md ./
COPY site/ site/
RUN python site/build.py --out /out/index.html

FROM nginx:1.27-alpine
COPY site/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /out/index.html /usr/share/nginx/html/index.html
HEALTHCHECK --interval=1m --timeout=5s --start-period=5s \
  CMD wget -qO /dev/null http://127.0.0.1/ || exit 1
