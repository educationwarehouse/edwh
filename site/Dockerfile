# Build context is the repository root (needs CHANGELOG.md), see docker-compose.yml.
FROM python:3.13-alpine
RUN apk add --no-cache curl
WORKDIR /srv
# baked-in fallback: served until the first fetch from CHANGELOG_URL succeeds
COPY CHANGELOG.md ./
COPY site/ site/
USER nobody
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=1m --timeout=5s --start-period=5s \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8000/healthz || exit 1
CMD ["python", "site/homepage_server.py"]
