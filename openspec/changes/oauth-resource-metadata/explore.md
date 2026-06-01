*This change was formed before openspec introduced `explore.md` as a required artifact. No genuine pre-spec audit trail exists; the substantive design choices are recorded in `design.md`. The Q&A below disambiguates one point that an independent reviewer might otherwise misread.*

## Decisions

### Decision: this-spec-owns-resource-url-field

- **Question**: `OAuthConfig` is established by `oauth-config-and-preflight`, but this change adds a new field `resource_url` to it. Why does field ownership cross the change boundary?
- **Answer**: Each change contributes only the `OAuthConfig` fields that the requirements it owns actually consume. `oauth-config-and-preflight` establishes the dataclass with the fields needed for activation gating and preflight (`issuer`, `audience`, `required_scopes`, `jwks_uri`, `allow_insecure_jwks`). It deliberately does NOT include `resource_url`, because resource_url is consumed only by the RFC 9728 metadata endpoint owned here. Keeping field ownership co-located with its requirement makes the field's tests live next to its consumer; an implementer touching the RFC 9728 endpoint also touches the field, and an implementer touching the activation gate does not.
- **Rationale**: One-place-for-each-thing review hygiene at the field level, not just the requirement level.
- **Affects**: tasks.md task 1.1 (adds the field to the dataclass); design.md note about field provenance.
