# Architecture

`trysac-tool-registry` provides a hardened, dependency-free registry and execution proxy for agent tools.

## Component Layout

```
+-------------------------------------------------------------+
|                          Registry                           |
|                                                             |
|  +---------------------+   +-----------------------------+  |
|  |   SemVer Resolver   |   |    Permission Guard         |  |
|  +----------+----------+   +--------------+--------------+  |
|             |                             |                 |
|             +--------------+--------------+                 |
|                            |                                |
|             +--------------v--------------+                 |
|             | Iterative Schema Validator  |                 |
|             +--------------+--------------+                 |
|                            |                                |
|             +--------------v--------------+                 |
|             |     Tool Execution (fn)     |                 |
|             +-----------------------------+                 |
+-------------------------------------------------------------+
```

## Invariant Pipeline Order

Every call to `Registry.invoke(ref, args, *, granted)` executes four stages in strict succession:

1. **Resolution (`resolve`)**: Matches prefix semver queries (`tool@MAJOR`, `tool@MAJOR.MINOR`, `tool@MAJOR.MINOR.PATCH`) to the highest registered version.
2. **Permissions Verification**: Inspects required `frozenset[str]` permissions against caller-provided `granted`. If any permission is ungranted, raises `RegistryError('permission_denied')` immediately carrying `.missing` without touching validator or invocation code.
3. **Schema Validation (`validate`)**: Iterative validation against bounded JSON Schema 2020-12 subset. Any failures abort invocation with `RegistryError('invalid_args')` carrying `.issues`.
4. **Execution & Telemetry**: Runs underlying tool callable `fn(**args)`. Telemetry callbacks capture execution duration and outcomes (`ok`, `error`, `permission_denied`, `invalid_args`) while strictly stripping caller argument payloads to prevent secret leakage.

## Security & Fail-Closed Schemas

- Schemas with unsupported keywords (e.g. `oneOf`, `$ref`, `pattern`) are rejected at registration with `invalid_schema` to guarantee that constraints are never silently ignored.
- Schema nesting depth is capped at 32.
- Maximum tool registrations are bounded (default 1,000) to protect against resource exhaustion.
