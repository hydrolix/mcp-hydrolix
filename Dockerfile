# use the official uv image (with matching python/alpine version) to construct the venv
FROM ghcr.io/astral-sh/uv:0.9.4-python3.13-alpine AS builder
# # Install `cc` (to build lz4 from source)
RUN apk add build-base

WORKDIR /app

# dependencies specifications
COPY pyproject.toml /app/
COPY uv.lock /app/
# And because uv sync likes to verify the README... for some reason...
COPY README.md /app/
# pyproject.toml now declares custom Hatchling metadata/build hooks in
# hatch_build.py, so resolving the project's (dynamic) metadata during uv sync
# requires this file to be present.
COPY hatch_build.py /app/

# produce .venv
RUN uv sync --locked

# begin definition of runtime container, relying on the venv made in builder
FROM python:3.13-alpine

# don't buffer log streams (docker adds enough delay)
ENV PYTHONUNBUFFERED=1

# don't cache pyc bytecode, since the container fs isn't persisted across restarts anyways
ENV PYTHONDONTWRITEBYTECODE=1

# Bind HTTP transport to all interfaces
ENV HYDROLIX_MCP_BIND_HOST=0.0.0.0
ENV HYDROLIX_MCP_SERVER_TRANSPORT=http

# declare that we expose port 8000
EXPOSE 8000

# Got a health check too
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD [ "wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1:8000/healthz" ]

RUN addgroup -g 1000 -S appgroup && \
  adduser -u 1000 -S appuser -G appgroup -h /app -s /sbin/nologin
USER appuser

WORKDIR /app


COPY --from=builder --chown=appuser:appgroup /app/.venv/ /app/.venv

COPY --chown=appuser:appgroup mcp_hydrolix/ /app/mcp_hydrolix
COPY --chown=appuser:appgroup pyproject.toml /app/

# Bake brand identity into the image. MCP_BRAND={hydrolix|trafficpeak}
# (default hydrolix) selects which _brand.py the running server reports --
# exactly like the wheel build; only mcp_hydrolix/_brand.py differs between
# brands. The server sources its startup log, outbound User-Agent, FastMCP
# server name, and admin-comment User token from these baked constants.
ARG MCP_BRAND=hydrolix
COPY --chown=appuser:appgroup hatch_build.py /app/hatch_build.py
RUN MCP_BRAND="${MCP_BRAND}" .venv/bin/python -c \
  "from hatch_build import brand_module_source, selected_brand; \
open('mcp_hydrolix/_brand.py','w').write(brand_module_source(selected_brand()))" \
  && .venv/bin/python -c "from mcp_hydrolix._brand import __dist_name__; print('baked brand:', __dist_name__)"

ENTRYPOINT [".venv/bin/python", "-m", "mcp_hydrolix.main"]
