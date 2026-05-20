"""Per-request service-account attribution logging (HDX-11151).

Emits one structured INFO log line per authenticated MCP request so log
aggregators can tie queries back to a specific service account.

This is a temporary stopgap. The fuller picture lives on query-head, which
will eventually log service-account queries directly; once that ships, this
middleware can be retired. See HDX-11151.

NOTE: the ticket also asks for the *creator's* email per request. Today neither
the JWT (``iss``, ``aud``, ``sub``, ``iat``, ``exp``, ``jti``) nor the
``ServiceAccount`` record in turbine carries that field, so it can't be logged
from the MCP side. It would land here too if turbine grows a ``created_by``
field and bakes it into the JWT claim set.

OpenSpec landed in the repo (#102) after this middleware was implemented; the
design here is captured in the PR description rather than as an OpenSpec
proposal/spec. Future features should use the OpenSpec workflow.
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext

from mcp_hydrolix.auth import AccessToken, ServiceAccountToken
from mcp_hydrolix.mcp_env import get_config


logger = logging.getLogger(__name__)


class SAAttributionMiddleware(Middleware):
    """Log one structured line per authenticated MCP request.

    The log line carries ``service_account_id`` (and ``tool_name`` for
    ``tools/call``) as top-level JSON fields via the ``JsonFormatter``
    extra-surfacing pass, so log processors can index/filter on them directly.

    Resolves the effective credential the same way ``create_hydrolix_client``
    does: a per-request bearer token (HTTP transport) takes precedence; if
    absent, falls back to the env-configured default credential (the typical
    stdio case under Claude Code, where ``HYDROLIX_TOKEN`` is set at server
    launch and there is no per-request auth context).
    """

    async def on_request(self, context: MiddlewareContext, call_next) -> Any:
        try:
            request_token = get_access_token()
            credential = None
            if isinstance(request_token, AccessToken):
                credential = request_token.as_credential()
            else:
                # No per-request auth context (stdio, or HTTP without a bearer).
                # Fall back to the env-configured default credential.
                try:
                    credential = get_config().creds_with(None)
                except ValueError:
                    # No default credential configured either — nothing to log.
                    pass

            # ``credential`` may be ``HydrolixCredential`` (abstract); only the
            # SA subtype carries ``service_account_id``. Guard rather than rely
            # on the broad except below so a non-SA credential (e.g.
            # UsernamePassword) skips cleanly without a misleading "logging
            # failed" debug line.
            if isinstance(credential, ServiceAccountToken):
                fields: dict[str, Any] = {
                    "service_account_id": credential.service_account_id,
                }
                if context.method == "tools/call":
                    tool_name = getattr(context.message, "name", None)
                    if tool_name is not None:
                        fields["tool_name"] = tool_name
                logger.info("mcp_request", extra=fields)
        except Exception:
            # Attribution is best-effort; never let a malformed token or other
            # logging-path failure turn into a request error.
            logger.debug("SA attribution logging failed", exc_info=True)

        return await call_next(context)
