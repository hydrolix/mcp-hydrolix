# use the official uv image (with matching python/alpine version) to construct the venv
FROM ghcr.io/astral-sh/uv:0.9.4-python3.13-alpine AS builder
# # Install `cc` (to build lz4 from source)
RUN apk add build-base

# Brand selection (mcp-hydrolix / mcp-trafficpeak), passed as a build-arg by the
# release workflow. Defaults to hydrolix so a plain `docker build` is unchanged.
ARG MCP_BRAND=hydrolix

WORKDIR /app

# dependencies specifications
COPY pyproject.toml /app/
COPY uv.lock /app/
# And because uv sync likes to verify the README... for some reason...
COPY README.md /app/

# produce .venv
RUN uv sync --locked

# Build the branded wheel and install it into the venv so the embedded
# distribution matches MCP_BRAND: this bakes mcp_hydrolix/_brand.py and the
# mcp-<brand> distribution metadata (so the runtime reports the right brand and
# version). The baked _brand.py is also stashed for the runtime stage, which
# copies the source tree over the venv package.
COPY hatch_build.py /app/
COPY mcp_hydrolix/ /app/mcp_hydrolix
RUN MCP_BRAND="${MCP_BRAND}" uv build --wheel \
  && uv pip install --no-deps --reinstall dist/*.whl \
  && mkdir -p /brand \
  && cp /app/.venv/lib/python3.13/site-packages/mcp_hydrolix/_brand.py /brand/_brand.py

# begin definition of runtime container, relying on the venv made in builder
FROM python:3.13-alpine

# don't buffer log streams (docker adds enough delay)
ENV PYTHONUNBUFFERED=1

# don't cache pyc bytecode, since the container fs isn't persisted across restarts anyways
ENV PYTHONDONTWRITEBYTECODE=1

# Bind HTTP transport to all interfaces. Set under both brand namespaces so that
# whichever namespace the dual-namespace resolver selects (HYDROLIX_* or
# TRAFFICPEAK_*, based on which *_URL the operator provides) picks up the
# in-container transport/bind defaults. (No customer-facing surface inspects the
# image's internal env, so carrying both prefixes here leaks nothing.)
ENV HYDROLIX_MCP_BIND_HOST=0.0.0.0
ENV HYDROLIX_MCP_SERVER_TRANSPORT=http
ENV TRAFFICPEAK_MCP_BIND_HOST=0.0.0.0
ENV TRAFFICPEAK_MCP_SERVER_TRANSPORT=http

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
# Overlay the build-time-baked brand module onto the copied source tree so the
# running server (which imports the source package) reports the built brand.
COPY --from=builder --chown=appuser:appgroup /brand/_brand.py /app/mcp_hydrolix/_brand.py
COPY --chown=appuser:appgroup pyproject.toml /app/

ENTRYPOINT [".venv/bin/python", "-m", "mcp_hydrolix.main"]
