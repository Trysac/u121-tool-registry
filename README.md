# trysac-tool-registry

[![CI](https://github.com/Trysac/u121-tool-registry/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u121-tool-registry/actions/workflows/ci.yml)

Versioned registry of agent tools with a bounded JSON Schema subset validator, semver resolution, permission checks before every call, and MCP-shaped export.

## Problem
Agent codebases accumulate tools whose schemas drift from their code, whose versions are implicit, and whose permissions are checked inside each tool. This library provides a centralized registry that validates arguments before calls, resolves versions explicitly, and enforces grants, making tool use auditable and robust.

## Installation
```bash
pip install trysac-tool-registry
```

## Usage
```python
from tool_registry import Registry, ToolSpec

reg = Registry()
reg.register(
    ToolSpec(
        name="read_file",
        version="1.0.0",
        description="read file",
        input_schema={
            "type": "object",
            "required": ["path"],
            "properties": {"path": {"type": "string"}},
        },
        permissions=frozenset({"fs.read"}),
        fn=lambda path: f"data from {path}",
    )
)
out = reg.invoke("read_file", {"path": "hello.txt"}, granted={"fs.read"})
print(out)
```

## Public API Summary
- **RegistryError Codes**: `invalid_name`, `invalid_version`, `duplicate_version`, `invalid_schema`, `not_found`, `permission_denied`, `invalid_args`, `too_many_tools`.
- **Limits**: Max 1,000 tools; max 32 nesting depth for schemas and values; max 100 validation issues; error messages are truncated at 200 characters.
- **Registry Options**: Accepts `clock` (default: `time.monotonic`) and `on_event` callback.

## Why not `jsonschema`?
Compared to using `jsonschema` with ad-hoc checks, `trysac-tool-registry` provides a single dependency-free contract for versions, grants, and arguments. It uses fail-closed schemas (unsupported keywords raise `invalid_schema`) to ensure constraints are never silently ignored.

[Security](docs/SECURITY.md)