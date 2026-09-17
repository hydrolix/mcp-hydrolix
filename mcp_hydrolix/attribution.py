"""Per-query attribution carried in ``hdx_query_admin_comment`` (HDX-12008).

Every query names the server that ran it and, when known, who and what asked,
so ``hydro.logs`` and ``hdx.active_queries`` can answer "who ran this" without
a schema change (the ``hydro.logs`` transform is frozen). The comment is
rendered as space-separated ``key: value`` tokens in a fixed order::

    User: <dist> version: <v> transport: <t> sub: <subject> agent: <client>/<ver>
    session: <id> trace: <traceparent> model: <m>

The first three tokens are the pseudo user-agent every Hydrolix connector
writes today and the usage analytics built on ``hydro.logs`` match on them, so
they never change shape or order. Request tokens are appended only when they
have a value. Colon and space are the separators, so neither may appear inside
a value: values are reduced to ``[A-Za-z0-9._/@-]`` and 64 characters, and the
whole string is capped at 512 bytes by dropping request tokens from the end,
so the descriptive ``model`` goes first and the join keys ``session`` and
``trace`` go last.

Trust differs by field. ``sub`` is the subject of the credential that
authenticates the query to the cluster, so a forged value produces no log row;
``hydro.logs.user`` is the authoritative record when the query head fills it.
The agent fields are attested by whoever set the header or ``_meta``, a
gateway in front of the server or any client that can set headers; sanitization
bounds them, nothing verifies them. All of it is observability, never
authorization.

This module is pure: vocabulary, sanitizer, renderer and a resolver over
already-extracted inputs. ``mcp_hydrolix.request_attribution`` reads the
transport once per request and calls in here.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any, Final, Mapping, Optional

ADMIN_COMMENT_MAX_BYTES: Final[int] = 512
FIELD_MAX_CHARS: Final[int] = 64
STATIC_FIELDS: Final[tuple[str, ...]] = ("User", "version", "transport")
# "sub" is the subject claim of the token the query ran as: a person's id behind a
# gateway that exchanges tokens per user, a service account otherwise. It is the key
# the gateway's audit log and the cluster's external identities join on, and it
# leaves room for an RFC 8693 "act" field beside it without renaming anything. The
# order is also the drop order under the byte budget, last token first, so the
# descriptive "model" is sacrificed before the join keys.
REQUEST_FIELDS: Final[tuple[str, ...]] = ("sub", "agent", "session", "trace", "model")
FIELD_ORDER: Final[tuple[str, ...]] = STATIC_FIELDS + REQUEST_FIELDS

# Request headers a gateway (or a client that can set headers) may use to hand the
# agent identity to this server. ``traceparent`` is the W3C header; the two
# ``X-Hdx-*`` names are this server's. Keys are lowercase, as FastMCP returns them.
AGENT_HEADER: Final[str] = "x-hdx-agent"
MODEL_HEADER: Final[str] = "x-hdx-model"
TRACEPARENT_HEADER: Final[str] = "traceparent"
# MCP recommends reverse-DNS prefixes for application keys in ``_meta``; the bare
# names stay accepted as a fallback for clients that predate the prefix.
META_AGENT_KEYS: Final[tuple[str, ...]] = ("io.hydrolix/agent", "agent")
META_MODEL_KEYS: Final[tuple[str, ...]] = ("io.hydrolix/model", "model")

_DISALLOWED = re.compile(r"[^A-Za-z0-9._/@-]")


def sanitize_value(value: Any) -> Optional[str]:
    """Reduce a field value to the allowed alphabet and length; None when empty."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _DISALLOWED.sub("_", text)[:FIELD_MAX_CHARS] or None


def _fit(tokens: list[str], keep: int) -> str:
    while len(tokens) > keep and len(" ".join(tokens).encode("utf-8")) > ADMIN_COMMENT_MAX_BYTES:
        tokens.pop()
    return " ".join(tokens)


def build_admin_comment(fields: Mapping[str, Any]) -> str:
    """Render ``key: value`` tokens in the fixed order, static identity first.

    Unknown keys are ignored and empty values are omitted. Used at startup for the
    static prefix; :func:`render_admin_comment` appends the request half per query.
    """
    tokens: list[str] = []
    static_count = 0
    for key in FIELD_ORDER:
        value = sanitize_value(fields.get(key))
        if value is not None:
            tokens.append(f"{key}: {value}")
            if key in STATIC_FIELDS:
                static_count += 1
    return _fit(tokens, keep=static_count)


@dataclass(frozen=True)
class RequestAttribution:
    """The request half of the comment, resolved once per MCP request."""

    sub: Optional[str] = None
    agent: Optional[str] = None
    model: Optional[str] = None
    session: Optional[str] = None
    trace: Optional[str] = None

    def as_fields(self) -> dict[str, Optional[str]]:
        return asdict(self)

    def with_sub(self, sub: Optional[str]) -> RequestAttribution:
        return replace(self, sub=sub)


def render_admin_comment(prefix: str, request: RequestAttribution) -> str:
    """Append the request tokens to the prebuilt static prefix, within the budget.

    ``prefix`` is the deployment's identity rendered once at startup, so the static
    fields are not sanitized again per query. Request tokens are dropped from the
    end until the string fits; the prefix is never dropped.
    """
    tokens = [prefix]
    for key in REQUEST_FIELDS:
        value = sanitize_value(getattr(request, key))
        if value is not None:
            tokens.append(f"{key}: {value}")
    return _fit(tokens, keep=1)


def _first_text(meta: Mapping[str, Any], keys: tuple[str, ...]) -> Optional[str]:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def resolve_request_attribution(
    headers: Mapping[str, str],
    meta: Mapping[str, Any],
    client_info: Optional[str],
    session_id: Optional[str],
) -> RequestAttribution:
    """Combine the extracted request inputs by precedence.

    Headers win because a gateway in front of the server sets them; the request's
    ``_meta`` and the ``initialize`` client info are supplied by the client itself.
    ``headers`` keys are lowercase, as FastMCP returns them. ``sub`` is not resolved
    here: it comes from the credential that authenticates the query.
    """
    agent = headers.get(AGENT_HEADER) or _first_text(meta, META_AGENT_KEYS) or client_info
    model = headers.get(MODEL_HEADER) or _first_text(meta, META_MODEL_KEYS)
    return RequestAttribution(
        agent=agent, model=model, session=session_id, trace=headers.get(TRACEPARENT_HEADER)
    )
