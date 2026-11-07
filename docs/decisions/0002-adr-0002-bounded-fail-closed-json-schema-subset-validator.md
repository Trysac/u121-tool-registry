# ADR 0002: Bounded Fail-Closed JSON Schema Subset Validator

Status: accepted (generated, pending human review)

## Context

Agent systems execute untrusted inputs across varying tool definitions. Existing external JSON Schema validators introduce runtime dependencies, support complex non-deterministic constructs ($ref, regex backtracking), and often fail silently or slowly on unbounded inputs.

## Decision

Implement a self-contained, standard-library-only validator for the JSON Schema 2020-12 core validation subset (type, properties, required, additionalProperties, items, enum, minLength, maxLength, minimum, maximum). Unknown schema keywords trigger 'invalid_schema' at registration time (fail-closed), schema and value parsing use explicit iterative stacks bounded at depth 32, and paths adhere strictly to RFC 6901 pointer syntax.

## Consequences

Eliminates third-party dependencies and schema drift vulnerabilities. Tools cannot use unsupported schema operators such as oneOf or regex patterns, but gain deterministic, bounded verification with auditable error reports.
