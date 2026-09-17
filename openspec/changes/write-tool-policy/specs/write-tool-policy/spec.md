## ADDED Requirements

### Requirement: Read Only Tool Annotations

Every tool registered on the server MUST declare `readOnlyHint=True` and `destructiveHint=False` unless its name is in the write-tool allow-list kept in the test suite; every name in that list MUST be a registered tool that declares `destructiveHint=True`.

#### Scenario: Every Registered Tool Is Read Only

- **WHEN** the registered tools are listed
- **THEN** each tool not in the allow-list has `readOnlyHint=True` and `destructiveHint=False`

#### Scenario: Write Tools Declare Destructive Hint

- **WHEN** the allow-list names a tool
- **THEN** that tool is registered and declares `destructiveHint=True`
