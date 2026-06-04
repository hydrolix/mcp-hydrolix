*This change was formed before openspec introduced `explore.md` as a required artifact. No genuine pre-spec audit trail exists; the substantive design choices are recorded in `design.md`. The Q&A below disambiguates one point that an independent reviewer might otherwise misread.*

## Decisions

### Decision: catch-runtimeerror-but-not-preflight-exceptions

- **Question**: The wiring function `_activate_oauth_if_configured()` catches `RuntimeError` from `asyncio.run()` and re-raises it, but does **not** catch network/HTTP/JSON exceptions from the preflight call inside that `asyncio.run`. Why the asymmetry?
- **Answer**: They mean different things. A `RuntimeError` from `asyncio.run()` itself means `create_app()` is being invoked under an already-running event loop (e.g., a future refactor moves activation behind a lifespan event, or a test harness drives `create_app()` from inside `pytest-asyncio`). That is a structural bug we want to surface loudly with a message pointing at the likely cause. Preflight exceptions (`httpx.HTTPError`, `json.JSONDecodeError`, missing-key `KeyError`, etc.) are owned by the `try_activate_oauth()` primitive, which catches them internally, emits the WARNING, and returns `None` per its fail-open contract; the wiring function only checks the return value.
- **Rationale**: The exception classes signal different failure domains. Preflight failure is operationally expected (network blips, IdP misconfiguration) and is handled by fail-open. Loop-state failure is a programming error and should crash the worker startup loudly.
- **Affects**: tasks.md task 2.1b's error-handling shape; the `asyncio.run` Decision in design.md.
