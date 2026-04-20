# OAuth 2.1 Authentication for mcp-hydrolix

This guide covers operator setup for OAuth bearer-token authentication on the
remote transports (HTTP, SSE). OAuth is **opt-in**: when
`HYDROLIX_OAUTH_ISSUER` is unset, the server behaves exactly as before and
continues to use the legacy credential chain (`HYDROLIX_TOKEN`,
`HYDROLIX_USER` / `HYDROLIX_PASSWORD`, per-request `Authorization: Bearer …`
or `?token=…`).

When activated, mcp-hydrolix becomes an OAuth 2.1 **resource server**:

- It verifies RS256 JWTs against Keycloak's JWKS before accepting any
  request.
- Verified tokens are forwarded verbatim to Hydrolix via
  `clickhouse-connect`'s `access_token` parameter.
- Invalid / expired / wrong-issuer / wrong-audience tokens produce `401
  Unauthorized` with a `WWW-Authenticate` challenge that advertises the
  protected-resource-metadata URL (RFC 9728).
- There is no fallback to env-var service-account credentials when a
  bearer token fails verification.

---

## 1. Keycloak client registration (one-time per cluster)

mcp-hydrolix does **not** need a client secret — it is a resource server, not
an OAuth client. But MCP-capable callers (Claude Desktop, MCP Inspector,
custom agents) do need a client registered in the realm so they can run the
PKCE authorization-code flow and obtain tokens with the right `aud` claim.

### Via the admin UI

1. Log in to Keycloak admin at `{cluster}/keycloak/admin`, realm
   `hydrolix-users`.
2. **Clients → Create client**
   - Client type: **OpenID Connect**
   - Client ID: `mcp-hydrolix`
3. **Capability config**
   - Client authentication: **Off** (public client — MCP desktop apps can't
     hold a secret; PKCE substitutes).
   - Authorization: Off.
   - Authentication flow: **Standard flow** on; everything else off.
4. **Login settings**
   - Valid redirect URIs: loopback patterns used by MCP clients, e.g.
     `http://127.0.0.1:*` and `http://localhost:*`.
   - Web origins: `+` (inherit).
5. **Advanced → Proof Key for Code Exchange**: `S256` (PKCE required).
6. **Audience mapper** — add a dedicated mapper so tokens issued to this
   client carry `aud: "mcp-hydrolix"`:
   - Client scopes → `mcp-hydrolix-dedicated` → Add mapper → By
     configuration → Audience
   - Included Client Audience: `mcp-hydrolix`
7. Verify: paste a freshly-issued token into https://jwt.io and confirm
   `iss` matches your `HYDROLIX_OAUTH_ISSUER` and `aud` is in the
   allowlist.

Commit the client registration to the cluster's infra-as-code (Turbine Helm
values) so it survives realm recreation.

### Via `kcadm.sh`

The companion file [`keycloak-mcp-client.json`](keycloak-mcp-client.json)
holds an importable definition. Adjust the redirect URIs for your
environment before running:

```bash
kcadm.sh config credentials --server https://{cluster}/keycloak \
    --realm master --user {admin} --password {pw}

kcadm.sh create clients -r hydrolix-users -f docs/keycloak-mcp-client.json
```

---

## 2. Environment variables

| Variable | Purpose | Default | Required | Notes |
|----------|---------|---------|----------|-------|
| `HYDROLIX_OAUTH_ISSUER` | OIDC issuer URL, e.g. `https://cluster.example.com/keycloak/realms/hydrolix-users`. **Presence activates OAuth mode.** | unset | Activator | Must match the `iss` claim verbatim. Use HTTPS in production. |
| `HYDROLIX_OAUTH_AUDIENCE` | Comma-separated allowlist of acceptable `aud` values. Tokens whose `aud` intersects this list pass the audience check. | unset | Required when OAuth activated | During transition: `mcp-hydrolix,config-api`. Target: `mcp-hydrolix` only. |
| `HYDROLIX_OAUTH_JWKS_URI` | Override JWKS endpoint. If unset, discovered from the issuer. In-cluster deployments use this for the Keycloak backchannel (see §4). | derived from issuer | Optional | Distinct from `HYDROLIX_OAUTH_ISSUER` — the `iss` claim still uses the external URL. |
| `HYDROLIX_OAUTH_REQUIRED_SCOPES` | Comma-separated scopes that must be present on every token. | unset | Optional | Leave empty during rollout; tighten after clients have migrated. |
| `HYDROLIX_OAUTH_RESOURCE_URL` | Base URL of this MCP server, used in RFC 9728 protected-resource metadata. | derived from bind host | Optional | Required when behind a reverse proxy that rewrites the `Host` header. Use the server origin only (e.g. `https://mcp.example.com`), not `…/mcp`. |
| `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS` | Set to `true` to allow `HYDROLIX_OAUTH_JWKS_URI` over plain HTTP (in-cluster backchannel). | `false` | Optional | **Only enable inside a trusted network segment.** Unset or `false` rejects HTTP JWKS URIs outright. |

Malformed configuration (e.g. issuer set but audience empty, HTTP JWKS URI
without the insecure flag) raises `OAuthConfigError` at startup and refuses
to launch — the operator must fix the env before the server will run.

Network failures during initial discovery or JWKS fetch are **fail-open**:
the server logs a single-line `WARNING`
(`OAuth configured but not activated: <reason>. Falling back to
service-account / username-password auth.`) and keeps running with the
legacy credential chain. Request-time verification failures remain
fail-closed.

---

## 3. Out-of-cluster deployment (laptop, VM, external host)

```bash
HYDROLIX_HOST=hydrolix.example.com
HYDROLIX_OAUTH_ISSUER=https://cluster.example.com/keycloak/realms/hydrolix-users
HYDROLIX_OAUTH_AUDIENCE=mcp-hydrolix,config-api
# HYDROLIX_OAUTH_JWKS_URI unset — derived from issuer
HYDROLIX_VERIFY=true
```

- JWKS is fetched over HTTPS directly from the external Keycloak URL.
- The `iss` check uses the same external URL.
- Strict TLS by default; `HYDROLIX_VERIFY` is honored as everywhere else.

---

## 4. In-cluster deployment (pod behind Traefik at `/mcp`)

```bash
HYDROLIX_HOST=hdxcli-xxxxxxxx-query-head.hydrolix.svc.cluster.local
HYDROLIX_OAUTH_ISSUER=https://cluster.example.com/keycloak/realms/hydrolix-users
HYDROLIX_OAUTH_AUDIENCE=mcp-hydrolix,config-api
HYDROLIX_OAUTH_JWKS_URI=http://keycloak:8080/keycloak/realms/hydrolix-users/protocol/openid-connect/certs
HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true
```

- `HYDROLIX_OAUTH_ISSUER` stays the **externally-visible** Keycloak URL —
  that's what Keycloak stamps into the `iss` claim, and what the user's
  browser hits during the PKCE login dance.
- `HYDROLIX_OAUTH_JWKS_URI` points to the in-cluster Service DNS so the
  MCP pod fetches JWKS over cluster DNS (faster, no egress, no TLS
  churn).
- `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` is mandatory for an HTTP JWKS
  URI — without it the config parser refuses the configuration at
  startup.
- Traefik's `unified_auth=True` on `/mcp` already validates incoming
  tokens. mcp-hydrolix's own JWT verification is defense-in-depth — it is
  also what makes the same container image portable to out-of-cluster
  deployments.

### Turbine integration

The recommended way to set these env vars in a Hydrolix cluster is via
Turbine's `McpOAuthConfig`:

```yaml
mcp_hydrolix:
  oauth:
    enabled: true
    audience: [mcp-hydrolix, config-api]
    use_backchannel_jwks: true
```

Existing clusters that do not set `mcp_hydrolix.oauth.enabled` are untouched.

---

## 5. Request-time precedence

When OAuth is active, every bearer (`Authorization: Bearer <t>` or
`?token=<t>`) is tried first against the OAuth `JWTVerifier`. If that
rejects it, the same token is tried against the legacy
`ServiceAccountToken` parser, so pre-OAuth callers keep working without
re-issuing tokens. Only if **both** verifiers reject the token does the
server return `401 + WWW-Authenticate`.

```
Request arrives at /mcp (OAuth activated)
├─ Authorization: Bearer <t>?
│   ├─ OAuth JWTVerifier accepts <t>?
│   │   └─ Yes → OAuthBearerToken. Token forwarded as access_token. STOP.
│   ├─ ServiceAccountToken parses <t>? (claims checked, signature not)
│   │   └─ Yes → ServiceAccountAccess. STOP.
│   └─ Neither accepts → continue.
├─ ?token=<t>?
│   └─ Same OAuth-then-SA chain.
├─ No credential presented
│   └─ 401 + WWW-Authenticate challenge (RFC 9728 resource_metadata).
```

Notes:
- The SA fallback uses the same JWT-claims validation path
  (`iss`, `iat`, `exp`) that pre-OAuth deployments have always used; the
  signature check is deferred to Hydrolix at query time.
- A junk bearer, expired JWT, or SA JWT with wrong issuer is rejected
  by both verifiers → `401`. There is no silent downgrade to
  `HYDROLIX_TOKEN` / `HYDROLIX_USER+HYDROLIX_PASSWORD` env-var creds on
  an HTTP request that presents a credential.
- Env-var credentials still apply to internal service-to-service paths
  that never hit the HTTP auth chain (stdio transport, direct
  `clickhouse-connect` use).

When OAuth is disabled or failed to activate, the decision tree collapses
to the legacy behaviour with no bearer verification layer.

---

## 6. Discovery endpoints

Once activated, the server exposes:

- `GET /.well-known/oauth-protected-resource/mcp` — RFC 9728
  protected-resource metadata. Returns `resource`,
  `authorization_servers`, `scopes_supported`, `bearer_methods_supported`,
  `resource_name`.
- `WWW-Authenticate: Bearer error="invalid_token",
  resource_metadata="…/.well-known/oauth-protected-resource/mcp"` on any
  401 response from an MCP endpoint.

MCP clients discover the authorization server via this metadata and start
their PKCE flow against the Keycloak client registered in §1.

---

## 7. Troubleshooting

**Server starts but logs `OAuth configured but not activated: …`.**
The issuer / audience env vars were set but discovery or JWKS fetch
failed. The server keeps running on legacy auth. Check the warning for the
specific URL and status code, then verify:

- Keycloak is reachable from the MCP pod / host.
- `HYDROLIX_OAUTH_ISSUER` is exactly the issuer Keycloak advertises (no
  trailing slash inconsistency).
- TLS / certificate chain is trusted (or set `HYDROLIX_VERIFY=false` in
  dev clusters).

**All clients get 401 even with a valid-looking token.**

- Decode the token at https://jwt.io (no signing secret needed for
  inspection only) and compare `iss` to `HYDROLIX_OAUTH_ISSUER` and `aud`
  to `HYDROLIX_OAUTH_AUDIENCE`. A trailing slash on `iss` counts as a
  mismatch.
- If `HYDROLIX_OAUTH_REQUIRED_SCOPES` is set, make sure the token's
  `scope` claim contains every required scope.

**Config refuses to start: HTTP JWKS URI.**
Either switch to HTTPS or set `HYDROLIX_OAUTH_ALLOW_INSECURE_JWKS=true` —
but only if the JWKS URI is inside a trusted network segment (e.g. a
Kubernetes cluster's pod network).

**Claude Desktop doesn't complete login.**

- Confirm the Keycloak client's redirect URIs include the loopback
  patterns (`http://127.0.0.1:*`, `http://localhost:*`).
- Confirm PKCE is set to `S256`, not plain.
- Confirm the audience mapper is attached to the client scope so tokens
  actually carry `aud: mcp-hydrolix`.
