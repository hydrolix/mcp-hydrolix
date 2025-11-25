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
  CMD [ "wget", "--no-verbose", "--tries=1", "--spider", "http://127.0.0.1:8000/health" ]

RUN addgroup -g 1000 -S appgroup && \
  adduser -u 1000 -S appuser -G appgroup -h /app -s /sbin/nologin
USER appuser

WORKDIR /app


COPY --from=builder --chown=appuser:appgroup /app/.venv/ /app/.venv

COPY --chown=appuser:appgroup mcp_hydrolix/ /app/mcp_hydrolix
COPY --chown=appuser:appgroup pyproject.toml /app/

ENTRYPOINT [".venv/bin/python", "-m", "mcp_hydrolix.main"]
