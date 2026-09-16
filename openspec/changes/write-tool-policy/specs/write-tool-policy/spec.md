## ADDED Requirements

### Requirement: Read Only Tool Annotations

Every tool registered on the server MUST declare `readOnlyHint=True` and `destructiveHint=False` unless its name is in `WRITE_TOOLS_REQUIRING_CONFIRMATION`; every name in that set MUST be a registered tool that declares `destructiveHint=True`.

#### Scenario: Every Registered Tool Is Read Only

- **WHEN** the registered tools are listed
- **THEN** each tool not in `WRITE_TOOLS_REQUIRING_CONFIRMATION` has `readOnlyHint=True` and `destructiveHint=False`

#### Scenario: Write Tools Declare Destructive Hint

- **WHEN** `WRITE_TOOLS_REQUIRING_CONFIRMATION` names a tool
- **THEN** that tool is registered and declares `destructiveHint=True`
