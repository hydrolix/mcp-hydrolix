<!--
  spec.md — the WHOLE contract for one change, in the examples-first format.
  Four sections, in this exact order: Intent → Examples → Constraints → Test
  plan. Examples replace prose: if a behavior is not in an example, it is not
  in the spec.

  Section headings are load-bearing — use them verbatim:
  - `### 1. Intent`
  - `### 2. Examples`
  - `### 3. Constraints`
  - `### 4. Test plan`

  Style:
  - Use uppercase RFC 2119 / BCP 14 keywords (MUST, MUST NOT, SHALL, SHOULD,
    MAY) for binding rules so humans and AI tools read them unambiguously.
  - Keep the whole file to <= 1 page. If it will not fit, split the change or
    escalate to a heavier schema (see schema.yaml "When To Add More Structure").

  Fill in the placeholders below. A concrete, filled-in mcp-hydrolix example is
  shown (commented out) at the END of this file — read it for the shape, then
  delete it. Do NOT leave the example in your finished spec.

  Anti-patterns:
  - Prose where an example would be clearer (examples replace prose).
  - No invalid-input example (every spec MUST show at least one).
  - Constraints that just restate an example (Constraints are for what
    examples CANNOT express).
  - Test code in the Test plan (name the test TYPES and cases; the
    implementation derives the code from the Examples).
-->

*<one-line summary, <= 25 words: what this change does>*

### 1. Intent

<!--
  1-3 sentences. WHAT and WHY, never HOW. Name the consumer of this behavior
  so a reviewer can sanity-check scope. Note graceful-degradation intent here
  if it applies.
-->

<intent — what behavior, why, and who consumes it>

### 2. Examples

*Each case below shows only the inputs that change from the Normal case; all
other inputs stay at their Normal values.*

**Normal**

- in: `<inputs>`
- out: `<expected output>`

**<Edge Case Name>** *(edge case)*

- in: `<only the inputs that change>`
- out: `<expected output>`

**<Invalid Case Name>** *(invalid input)*

- in: `<only the inputs that change>`
- out: `<NamedError>`

### 3. Constraints

<!--
  Highest value-per-line section — spend effort here. Invariants and "do NOT"
  rules that examples cannot express: fixed signatures, performance/concurrency
  bounds, purity rules, and any intentional code that LOOKS like a mistake.
-->

- <MUST / MUST NOT rule the examples cannot express>

### 4. Test plan

<!--
  Name the test TYPES and the non-obvious cases. Do NOT write test code — the
  implementation derives it from the Examples. Every Example above MUST be
  reachable by at least one test named here.
-->

- Unit: each Example above as a case.
- <other test type — boundary / regression / property — and the cases it covers>

<!--
  ILLUSTRATIVE EXAMPLE (mcp-hydrolix) — for shape only. DELETE before committing;
  do not ship this in a real spec.

  ### 1. Intent

  Normalize a SQL statement submitted to the `run_select_query` MCP tool before
  it reaches Hydrolix. Used by the query-tool handler. MUST reject mutations and
  bound otherwise-unbounded result sets.

  ### 2. Examples

  *Each case shows only the inputs that change from Normal; others stay at Normal.*

  **Normal**

  - in: `query="SELECT host FROM logs.access WHERE ts > now() - 3600", limit=100`
  - out: `{ ok: true, sql: "SELECT host FROM logs.access WHERE ts > now() - 3600 LIMIT 100" }`

  **Caller Already Set A Limit** *(edge case)*

  - in: `query="SELECT host FROM logs.access LIMIT 5"`
  - out: `{ ok: true, sql: "SELECT host FROM logs.access LIMIT 5" }`   (existing LIMIT preserved)

  **Non-Select Statement** *(invalid input)*

  - in: `query="INSERT INTO logs.access VALUES ('x')"`
  - out: `ValidationError("only SELECT / WITH queries are permitted")`

  ### 3. Constraints

  - Do NOT permit mutations — only `SELECT` and `WITH … SELECT`; reject
    INSERT / ALTER / DROP / TRUNCATE / etc.
  - Do NOT override a `LIMIT` the caller already provided.
  - Pure function: no DB I/O — the handler executes the returned SQL separately.

  ### 4. Test plan

  - Unit: each Example above as a case.
  - Unit: statements with leading comments / whitespace are still classified
    correctly (the SELECT-vs-mutation check must not be fooled by them).
  - Regression: queries already exercised in `tests/` still normalize
    byte-identically.
-->
