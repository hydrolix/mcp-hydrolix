*2 phases, 4 tasks.*

**Tracking:** HDX-12410

## 1. Implementation

- [x] 1.1 Add `allow_token_query_param` to `HydrolixConfig` (default true, only `false` disables) and the startup log [implements: request-credentials/token-query-parameter-opt-out, design/default-on-opt-out] — verify: `pytest -q tests/test_token_query_param.py -k "default or explicit or logs"` green
- [x] 1.2 Gate `GetParamAuthBackend` behind the flag in `HydrolixCredentialChain.backends()` and pass the flag from `mcp_server` [implements: request-credentials/token-query-parameter-opt-out, design/default-on-opt-out] — verify: `grep -n allow_token_query_param mcp_hydrolix/auth/mcp_providers.py mcp_hydrolix/mcp_server.py` non-empty

## 2. Tests and docs

- [x] 2.1 `tests/test_token_query_param.py` covers every scenario [implements: meta/tests] — verify: `pytest -q tests/test_token_query_param.py` green
- [x] 2.2 Document the variable in `docs/CONFIG.md` ("Per-request credentials") and the README authentication section [implements: meta/docs] — verify: `grep -n HYDROLIX_ALLOW_TOKEN_QUERY_PARAM README.md docs/CONFIG.md` non-empty
