*Every registered tool is read-only unless it is declared a write tool that requires confirmation.*

## ADDED Requirements

### Requirement: Read Only Tool Annotations

Every tool registered on the server MUST declare `readOnlyHint=True` and `destructiveHint=False` unless its name is in `WRITE_TOOLS_REQUIRING_CONFIRMATION`; every name in that set MUST be a registered tool declaring `destructiveHint=True`.
<!-- settle: explore/write-tool-rule -->

#### Scenario: Every Registered Tool Is Read Only

- **WHEN** the registered tools are listed
- **THEN** each tool not in `WRITE_TOOLS_REQUIRING_CONFIRMATION` has `readOnlyHint=True` and `destructiveHint=False`

#### Scenario: Write Tools Declare Destructive Hint

- **WHEN** the registered tools are listed
- **THEN** every name in `WRITE_TOOLS_REQUIRING_CONFIRMATION` is registered
- **AND** declares `destructiveHint=True`
