# Testing

## Existing Tests
- `tests/test_tool_registry.py`: Covers the full suite of acceptance criteria, including semver resolution (registry behavior with multiple versions), permission enforcement (granted vs missing), and JSON schema validation logic (including nested structures and issue reporting).

## Policy
- Branch coverage must remain at or above 80%.
- Tests are deterministic: no network calls, no reliance on wall clock, no test-order dependencies.