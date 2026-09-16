"""Per-query attribution carried in ``hdx_query_admin_comment`` (HDX-12008).

Every query names the server that ran it and, when known, who and what asked,
so ``hydro.logs`` and ``hdx.active_queries`` can answer "who ran this" without
a schema change (the ``hydro.logs`` transform is frozen). The comment is
rendered as space-separated ``key: value`` tokens in a fixed order::

    User: <dist> version: <v> transport: <t> sub: <subject> agent: <client>/<ver>
    model: <m> session: <id> trace: <traceparent>

The first three tokens are the pseudo user-agent every Hydrolix connector
writes today and the usage analytics built on ``hydro.logs`` match on them, so
they never change shape or order. Request tokens are appended only when they
have a value. Colon and space are the separators, so neither may appear inside
a value: values are reduced to ``[A-Za-z0-9._/@-]`` and 64 characters, and the
whole string is capped at 512 bytes by dropping request tokens from the end.

The request fields come from a gateway in front of the server (MCPKA) or from
a client that can set headers; they are observability, never authorization.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any, Final, Mapping, Optional

from fastmcp.server.dependencies import get_context, get_http_headers

logger = logging.getLogger(__name__)

ADMIN_COMMENT_MAX_BYTES: Final[int] = 512
FIELD_MAX_CHARS: Final[int] = 64
STATIC_FIELDS: Final[tuple[str, ...]] = ("User", "version", "transport")
# "sub" is the subject claim of the token the query ran as: a person's id behind a
# gateway that exchanges tokens per user, a service account otherwise. It is the key
# the gateway's audit log and the cluster's external identities join on, and it
# leaves room for an RFC 8693 "act" field beside it without renaming anything.
REQUEST_FIELDS: Final[tuple[str, ...]] = ("sub", "agent", "model", "session", "trace")
FIELD_ORDER: Final[tuple[str, ...]] = STATIC_FIELDS + REQUEST_FIELDS

# Request headers a gateway (or a client that can set headers) may use to hand the
# agent identity to this server. ``traceparent`` and ``Mcp-Session-Id`` are the
# W3C and MCP standard headers; the two ``X-Hdx-*`` names are this server's.
AGENT_HEADER: Final[str] = "x-hdx-agent"
MODEL_HEADER: Final[str] = "x-hdx-model"
TRACEPARENT_HEADER: Final[str] = "traceparent"
SESSION_HEADER: Final[str] = "mcp-session-id"
_ATTRIBUTION_HEADERS: Final[frozenset[str]] = frozenset(
    {AGENT_HEADER, MODEL_HEADER, TRACEPARENT_HEADER, SESSION_HEADER}
)

_DISALLOWED = re.compile(r"[^A-Za-z0-9._/@-]")


def sanitize_value(value: Any) -> Optional[str]:
    """Reduce a field value to the allowed alphabet and length; None when empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _DISALLOWED.sub("_", text)[:FIELD_MAX_CHARS] or None


def build_admin_comment(fields: Mapping[str, Any]) -> str:
    """Render ``key: value`` tokens in the fixed order, static identity first.

    Unknown keys are ignored and empty values are omitted. The string is trimmed
    to :data:`ADMIN_COMMENT_MAX_BYTES` by dropping request tokens from the end;
    the static identity is never dropped.
    """
    tokens: list[str] = []
    for key in FIELD_ORDER:
        value = sanitize_value(fields.get(key))
        if value is not None:
            tokens.append(f"{key}: {value}")
    while (
        len(tokens) > len(STATIC_FIELDS)
        and len(" ".join(tokens).encode("utf-8")) > ADMIN_COMMENT_MAX_BYTES
    ):
        tokens.pop()
    return " ".join(tokens)


@dataclass(frozen=True)
class RequestAttribution:
    """Request-side attribution fields resolved for the current MCP request."""

    sub: Optional[str] = None
    agent: Optional[str] = None
    model: Optional[str] = None
    session: Optional[str] = None
    trace: Optional[str] = None

    def as_fields(self) -> dict[str, Optional[str]]:
        return asdict(self)


def _meta_value(meta: Any, key: str) -> Optional[str]:
    """Read a string field from the request's MCP ``_meta`` (extra keys allowed)."""
    if meta is None:
        return None
    extra = getattr(meta, "model_extra", None) or {}
    value = extra.get(key, getattr(meta, key, None))
    return value if isinstance(value, str) else None


def _client_info(ctx: Any) -> Optional[str]:
    """``<name>/<version>`` from the session's ``initialize`` params, when kept."""
    try:
        params = ctx.session.client_params
    except Exception:
        return None
    info = getattr(params, "clientInfo", None)
    name = getattr(info, "name", None)
    if not name:
        return None
    version = getattr(info, "version", None)
    return f"{name}/{version}" if version else str(name)


def gather_request_attribution(
    credential: Any, *, transport: str, use_session_id: bool
) -> RequestAttribution:
    """Resolve the attribution fields for the current request, best-effort.

    ``sub`` is the ``sub`` claim of the bearer credential the request ran as, or
    the username of a basic-auth credential. Agent fields come, in precedence
    order, from the request headers a gateway sets, from the request's MCP
    ``_meta``, and from the session's ``initialize`` client info. Nothing here
    raises: attribution is observability and must never fail a query.
    """
    sub = getattr(credential, "service_account_id", None) or getattr(credential, "username", None)
    agent = model = session = trace = None
    try:
        headers = {
            k.lower(): v for k, v in get_http_headers(include=set(_ATTRIBUTION_HEADERS)).items()
        }
        agent = headers.get(AGENT_HEADER)
        model = headers.get(MODEL_HEADER)
        trace = headers.get(TRACEPARENT_HEADER)
        session = headers.get(SESSION_HEADER)
    except Exception:
        logger.debug("attribution: headers unavailable", exc_info=True)
    try:
        ctx = get_context()
    except Exception:
        ctx = None
    if ctx is not None:
        try:
            request_ctx = ctx.request_context
            meta = getattr(request_ctx, "meta", None) if request_ctx is not None else None
            agent = agent or _meta_value(meta, "agent")
            model = model or _meta_value(meta, "model")
            agent = agent or _client_info(ctx)
            if session is None and use_session_id and transport == "stdio":
                session = ctx.session_id
        except Exception:
            logger.debug("attribution: context fields unavailable", exc_info=True)
    return RequestAttribution(sub=sub, agent=agent, model=model, session=session, trace=trace)
