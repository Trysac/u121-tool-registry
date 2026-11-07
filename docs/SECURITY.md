# Security notes

## Threat model

### Defended
- **Supply chain**: No runtime dependencies. Minimal workflow permissions.
- **Accidental exposure**: Gitleaks used in CI gates.
- **Hostile input**: All inputs are subjected to schema validation and type checking. Exceptions are raised for invalid inputs.

### Not Defended
- **Sandboxing**: This registry is not a sandbox; registered tools (`fn`) execute with the same privileges as the calling process.
- **I/O Security**: The registry acts as a proxy/guard but does not restrict I/O performed by the tool handlers themselves.

### Limits
- Max schema/value depth: 32.
- Max tool registry capacity: 1000.
- Validation: Fail-closed (unknown keywords raise `invalid_schema`).

[README](../README.md)