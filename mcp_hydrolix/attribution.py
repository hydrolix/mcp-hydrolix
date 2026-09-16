"""Per-query attribution carried in the existing Hydrolix query settings (HDX-12008).

Every query names the human principal and the agent that issued it, so
``hydro.logs`` and ``hdx.active_queries`` can answer "who ran this" without a
schema change (the ``hydro.logs`` transform is frozen). The vocabulary and the
length budget are the ones decided under CFB-1787 (plan section 8, row 9):

    app=<dist>/<version> transport=<t> user=<sub> agent=<client>/<ver>
    model=<m> session=<id> trace=<traceparent>

Values are restricted to ``[A-Za-z0-9._:/@-]``, 64 characters each; a field
with no value is omitted rather than emitted empty; the whole string is capped
at 512 bytes with the trailing fields dropped first. Consumers parse with a
regex on ``key=``.
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
PURPOSE_MAX_CHARS: Final[int] = 256
FIELD_ORDER: Final[tuple[str, ...]] = (
    "app",
    "transport",
    "user",
    "agent",
    "model",
    "session",
    "trace",
)

# Request headers a gateway (or a client that can set headers) may use to hand
# the agent identity to this server. ``traceparent`` and ``Mcp-Session-Id`` are
# the standard W3C and MCP headers; the two ``X-Hdx-*`` names are this server's.
AGENT_HEADER: Final[str] = "x-hdx-agent"
MODEL_HEADER: Final[str] = "x-hdx-model"
TRACEPARENT_HEADER: Final[str] = "traceparent"
SESSION_HEADER: Final[str] = "mcp-session-id"
_ATTRIBUTION_HEADERS: Final[frozenset[str]] = frozenset(
    {AGENT_HEADER, MODEL_HEADER, TRACEPARENT_HEADER, SESSION_HEADER}
)

_DISALLOWED = re.compile(r"[^A-Za-z0-9._:/@-]")


def sanitize_value(value: Any) -> Optional[str]:
    """Reduce a field value to the allowed alphabet and length; None when empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _DISALLOWED.sub("_", text)[:FIELD_MAX_CHARS] or None


def build_admin_comment(fields: Mapping[str, Any]) -> str:
    """Render the ``key=value`` admin comment in the fixed field order.

    Unknown keys are ignored, empty values are omitted, and the string is
    trimmed to :data:`ADMIN_COMMENT_MAX_BYTES` by dropping trailing fields.
    """
    tokens: list[str] = []
    for key in FIELD_ORDER:
        value = sanitize_value(fields.get(key))
        if value is not None:
            tokens.append(f"{key}={value}")
    while tokens and len(" ".join(tokens).encode("utf-8")) > ADMIN_COMMENT_MAX_BYTES:
        tokens.pop()
    return " ".join(tokens)


def sanitize_purpose(purpose: Optional[str]) -> Optional[str]:
    """Trim the caller's free-text purpose for ``hdx_query_comment``; None when empty."""
    if purpose is None:
        return None
    text = " ".join(purpose.split())
    return text[:PURPOSE_MAX_CHARS] or None


@dataclass(frozen=True)
class RequestAttribution:
    """Agent-side attribution fields resolved for the current MCP request."""

    user: Optional[str] = None
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
    """``<name>/<version>`` from the session's ``initialize`` params, when the transport kept them."""
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

    ``user`` is the ``sub`` of the bearer credential the request carried (the
    per-user token under the gateway, the service account otherwise), or the
    username of a basic-auth credential. Agent fields come, in precedence
    order, from the request headers a gateway sets, from the request's MCP
    ``_meta``, and from the session's ``initialize`` client info. Nothing here
    raises: attribution is observability and must never fail a query.
    """
    user = getattr(credential, "service_account_id", None) or getattr(credential, "username", None)
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
    return RequestAttribution(user=user, agent=agent, model=model, session=session, trace=trace)
