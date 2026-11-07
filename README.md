# tool-registry

[![PyPI version](https://img.shields.io/pypi/v/trysac-tool-registry)](https://pypi.org/project/trysac-tool-registry/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-tool-registry)](LICENSE)
[![CI](https://github.com/Trysac/u121-tool-registry/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u121-tool-registry/actions/workflows/ci.yml)

Versioned registry of agent tools with a bounded JSON Schema subset validator, semver resolution, permission checks before every call and MCP-shaped export

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-tool-registry
# or
uv add trysac-tool-registry
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import tool_registry

# normalize() trims surrounding whitespace and lower-cases the text.
print(tool_registry.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    tool_registry.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
