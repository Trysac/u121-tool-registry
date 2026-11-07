"""Versioned registry of agent tools with schema validation, semver resolution, and permissions."""

from __future__ import annotations

import builtins
import logging
import math
import re
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "Issue",
    "Registry",
    "RegistryError",
    "ToolSpec",
    "__version__",
    "validate",
]

__version__ = "0.1.0"

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")
_VERSION_RE = re.compile(r"^(0|[1-9]P[0-9]*)P.(0|[1-9]P[0-9]*)P.(0|[1-9]P[0-9]*)$".replace("P", ""))
_VERSION_PART_RE = re.compile(r"^(0|[1-9][0-9]*)$")

_ALLOWED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "enum",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "title",
        "description",
        "default",
    }
)

_ALLOWED_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})

MAX_SCHEMA_DEPTH = 32
MAX_VALUE_DEPTH = 32
MAX_ISSUES = 100
MAX_ERROR_MSG_LEN = 200


ErrorCode = Literal[
    "invalid_name",
    "invalid_version",
    "duplicate_version",
    "invalid_schema",
    "not_found",
    "permission_denied",
    "invalid_args",
    "too_many_tools",
]


class RegistryError(Exception):
    """Base exception for all registry operations."""

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        missing: tuple[str, ...] = (),
        issues: tuple[Issue, ...] = (),
    ) -> None:
        self.code: ErrorCode = code
        self.missing: tuple[str, ...] = missing
        self.issues: tuple[Issue, ...] = issues
        truncated_msg = message[:MAX_ERROR_MSG_LEN] if message is not None else code
        super().__init__(truncated_msg)


@dataclass(frozen=True)
class Issue:
    """A single validation issue at a JSON pointer path."""

    path: str
    keyword: str


@dataclass(frozen=True)
class ToolSpec:
    """Specification of a registered tool."""

    name: str
    version: str
    description: str
    input_schema: Mapping[str, Any]
    permissions: frozenset[str]
    fn: Callable[..., Any]


def _escape_json_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def _parse_version(version_str: str) -> tuple[int, int, int]:
    match = _VERSION_RE.fullmatch(version_str)
    if not match:
        raise RegistryError(
            "invalid_version",
            f"Version '{version_str}' does not match strict MAJOR.MINOR.PATCH format.",
        )
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _validate_schema_definition(
    schema: Mapping[str, Any], depth_limit: int = MAX_SCHEMA_DEPTH
) -> None:
    """Validate schema keywords and structure iteratively up to depth limit."""
    if not isinstance(schema, Mapping):
        raise RegistryError("invalid_schema", "Schema root must be a mapping/object.")

    root_type = schema.get("type")
    if root_type != "object" and root_type != ["object"]:
        raise RegistryError("invalid_schema", "The root schema must have type 'object'.")

    # Iterative stack-based verification: (subschema, current_depth)
    stack: list[tuple[Mapping[str, Any], int]] = [(schema, 1)]
    while stack:
        curr, depth = stack.pop()
        if depth > depth_limit:
            raise RegistryError(
                "invalid_schema",
                f"Schema nesting exceeds maximum allowed depth of {depth_limit}.",
            )

        for key in curr:
            if key not in _ALLOWED_KEYWORDS:
                raise RegistryError(
                    "invalid_schema",
                    f"Unsupported or forbidden schema keyword '{key}'.",
                )

        # Check 'type' keyword
        if "type" in curr:
            t = curr["type"]
            if isinstance(t, str):
                if t not in _ALLOWED_TYPES:
                    raise RegistryError("invalid_schema", f"Invalid schema type '{t}'.")
            elif isinstance(t, list):
                if not t or not all(isinstance(item, str) and item in _ALLOWED_TYPES for item in t):
                    raise RegistryError("invalid_schema", f"Invalid schema types in list: {t}.")
            else:
                raise RegistryError(
                    "invalid_schema",
                    "'type' must be a string or list of strings.",
                )

        # Check 'properties'
        if "properties" in curr:
            props = curr["properties"]
            if not isinstance(props, Mapping):
                raise RegistryError("invalid_schema", "'properties' must be a mapping.")
            for prop_name, prop_schema in props.items():
                if not isinstance(prop_name, str):
                    raise RegistryError("invalid_schema", "Property names must be strings.")
                if not isinstance(prop_schema, Mapping):
                    raise RegistryError(
                        "invalid_schema",
                        f"Property schema for '{prop_name}' must be a mapping.",
                    )
                stack.append((prop_schema, depth + 1))

        # Check 'required'
        if "required" in curr:
            req = curr["required"]
            if not isinstance(req, (list, tuple)) or not all(isinstance(r, str) for r in req):
                raise RegistryError("invalid_schema", "'required' must be a list/tuple of strings.")

        # Check 'additionalProperties'
        if "additionalProperties" in curr:
            add_props = curr["additionalProperties"]
            if not isinstance(add_props, bool):
                raise RegistryError("invalid_schema", "'additionalProperties' must be a bool.")

        # Check 'items'
        if "items" in curr:
            items = curr["items"]
            if not isinstance(items, Mapping):
                raise RegistryError("invalid_schema", "'items' must be a single schema mapping.")
            stack.append((items, depth + 1))

        # Check 'enum'
        if "enum" in curr:
            enum_val = curr["enum"]
            if not isinstance(enum_val, (list, tuple)):
                raise RegistryError("invalid_schema", "'enum' must be a list or tuple.")

        # Check minLength / maxLength
        for kw in ("minLength", "maxLength"):
            if kw in curr:
                val = curr[kw]
                if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                    raise RegistryError(
                        "invalid_schema",
                        f"'{kw}' must be a non-negative integer.",
                    )

        # Check minimum / maximum
        for kw in ("minimum", "maximum"):
            if kw in curr:
                val = curr[kw]
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise RegistryError("invalid_schema", f"'{kw}' must be a number.")


def _is_integer(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, int):
        return True
    if isinstance(val, float) and math.isfinite(val):
        return val.is_integer()
    return False


def _is_number(val: Any) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return math.isfinite(val)
    return False


def _match_type(expected_type: str, val: Any) -> bool:
    if expected_type == "object":
        return isinstance(val, Mapping) and all(isinstance(k, str) for k in val)
    if expected_type == "array":
        return isinstance(val, (list, tuple))
    if expected_type == "string":
        return isinstance(val, str)
    if expected_type == "integer":
        return _is_integer(val)
    if expected_type == "number":
        return _is_number(val)
    if expected_type == "boolean":
        return isinstance(val, bool)
    if expected_type == "null":
        return val is None
    return False


def _enum_contains(enum_list: list[Any] | tuple[Any, ...], val: Any) -> bool:
    """Strict equality check for enum items handling float/int distinctions and bools."""
    for candidate in enum_list:
        if type(candidate) is bool or type(val) is bool:
            if candidate is val:
                return True
        elif isinstance(candidate, (int, float)) and isinstance(val, (int, float)):
            if math.isfinite(candidate) and math.isfinite(val) and candidate == val:
                return True
        elif candidate == val:
            return True
    return False


def validate(schema: Mapping[str, Any], value: Any) -> list[Issue]:
    """Validate a Python value against a supported JSON Schema subset."""
    # First verify schema conformance
    _validate_schema_definition(schema)

    issues: list[Issue] = []

    # (schema_node, value_node, current_path, depth)
    stack: list[tuple[Mapping[str, Any], Any, str, int]] = [(schema, value, "", 1)]

    while stack:
        curr_schema, curr_val, path, depth = stack.pop()
        if depth > MAX_VALUE_DEPTH:
            issues.append(Issue(path, "depthLimitExceeded"))
            if len(issues) >= MAX_ISSUES:
                break
            continue

        # 1. Type validation
        if "type" in curr_schema:
            types = curr_schema["type"]
            type_list = [types] if isinstance(types, str) else list(types)

            matched = any(_match_type(t, curr_val) for t in type_list)
            if not matched:
                issues.append(Issue(path, "type"))
                if len(issues) >= MAX_ISSUES:
                    break
                # If type does not match, skip further value-specific keyword checks on this node
                continue

        # 2. Enum check
        if "enum" in curr_schema and not _enum_contains(curr_schema["enum"], curr_val):
            issues.append(Issue(path, "enum"))
            if len(issues) >= MAX_ISSUES:
                break

        # 3. String minLength / maxLength (measured in code points)
        if isinstance(curr_val, str):
            length = len(curr_val)
            if "minLength" in curr_schema and length < curr_schema["minLength"]:
                issues.append(Issue(path, "minLength"))
                if len(issues) >= MAX_ISSUES:
                    break
            if "maxLength" in curr_schema and length > curr_schema["maxLength"]:
                issues.append(Issue(path, "maxLength"))
                if len(issues) >= MAX_ISSUES:
                    break

        # 4. Number minimum / maximum
        if not isinstance(curr_val, bool) and isinstance(curr_val, (int, float)):
            if "minimum" in curr_schema and curr_val < curr_schema["minimum"]:
                issues.append(Issue(path, "minimum"))
                if len(issues) >= MAX_ISSUES:
                    break
            if "maximum" in curr_schema and curr_val > curr_schema["maximum"]:
                issues.append(Issue(path, "maximum"))
                if len(issues) >= MAX_ISSUES:
                    break

        # 5. Object validation: required, properties, additionalProperties
        if isinstance(curr_val, Mapping) and all(isinstance(k, str) for k in curr_val):
            # Check required
            if "required" in curr_schema:
                for req_key in curr_schema["required"]:
                    if req_key not in curr_val:
                        prop_path = f"{path}/{_escape_json_pointer_segment(req_key)}"
                        issues.append(Issue(prop_path, "required"))
                        if len(issues) >= MAX_ISSUES:
                            break
                if len(issues) >= MAX_ISSUES:
                    break

            # Check additionalProperties
            props = curr_schema.get("properties", {})
            additional_allowed = curr_schema.get("additionalProperties", True)
            if not additional_allowed:
                for key in curr_val:
                    if key not in props:
                        prop_path = f"{path}/{_escape_json_pointer_segment(key)}"
                        issues.append(Issue(prop_path, "additionalProperties"))
                        if len(issues) >= MAX_ISSUES:
                            break
                if len(issues) >= MAX_ISSUES:
                    break

            # Schedule property validation
            # Process sorted for determinism
            for key in sorted(curr_val.keys()):
                if key in props:
                    prop_schema = props[key]
                    prop_path = f"{path}/{_escape_json_pointer_segment(key)}"
                    stack.append((prop_schema, curr_val[key], prop_path, depth + 1))

        # 6. Array validation: items
        elif isinstance(curr_val, (list, tuple)) and "items" in curr_schema:
            item_schema = curr_schema["items"]
            for idx, item_val in enumerate(curr_val):
                elem_path = f"{path}/{idx}"
                stack.append((item_schema, item_val, elem_path, depth + 1))

    # Sort issues by (path, keyword)
    issues.sort(key=lambda x: (x.path, x.keyword))
    return issues[:MAX_ISSUES]


class Registry:
    """Thread-safe, bounded, versioned registry for agent tools."""

    def __init__(
        self,
        *,
        max_tools: int = 1000,
        clock: Callable[[], float] = time.monotonic,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._max_tools = max_tools
        self._clock = clock
        self._on_event = on_event
        # Storage: tool_name -> dict of (M, m, p) -> ToolSpec
        self._tools: dict[str, dict[tuple[int, int, int], ToolSpec]] = {}
        self._total_specs_count = 0

    def register(self, spec: ToolSpec) -> None:
        """Register a tool specification."""
        if not _NAME_RE.fullmatch(spec.name):
            raise RegistryError(
                "invalid_name",
                f"Name '{spec.name}' must match pattern ^[a-z][a-z0-9_]{{0,63}}$",
            )

        parsed_version = _parse_version(spec.version)

        for perm in spec.permissions:
            if not _PERMISSION_RE.fullmatch(perm):
                raise RegistryError(
                    "invalid_schema",
                    f"Permission '{perm}' must match pattern ^[a-z][a-z0-9_.:-]{{0,63}}$",
                )

        _validate_schema_definition(spec.input_schema)

        if self._total_specs_count >= self._max_tools:
            raise RegistryError(
                "too_many_tools",
                f"Registry has reached maximum capacity of {self._max_tools} tools.",
            )

        name_versions = self._tools.setdefault(spec.name, {})
        if parsed_version in name_versions:
            raise RegistryError(
                "duplicate_version",
                f"Tool '{spec.name}' version '{spec.version}' is already registered.",
            )

        name_versions[parsed_version] = spec
        self._total_specs_count += 1

    def resolve(self, ref: str) -> ToolSpec:
        """Resolve a tool reference ('name', 'name@M', 'name@M.m', 'name@M.m.p')."""
        if "@" in ref:
            name, prefix = ref.split("@", 1)
            parts_str = prefix.split(".")
            if len(parts_str) > 3 or not parts_str:
                raise RegistryError("invalid_version", f"Invalid version prefix '{prefix}'.")
            prefix_parts: list[int] = []
            for p in parts_str:
                if not _VERSION_PART_RE.fullmatch(p):
                    raise RegistryError(
                        "invalid_version",
                        f"Invalid version prefix component '{p}'.",
                    )
                prefix_parts.append(int(p))
            match_prefix = tuple(prefix_parts)
        else:
            name = ref
            match_prefix = ()

        if not _NAME_RE.fullmatch(name):
            raise RegistryError("invalid_name", f"Invalid tool name '{name}' in ref.")

        versions_map = self._tools.get(name)
        if not versions_map:
            raise RegistryError("not_found", f"No tool found registered with name '{name}'.")

        # Filter matching versions
        candidates: list[tuple[int, int, int]] = []
        for v in versions_map:
            if v[: len(match_prefix)] == match_prefix:
                candidates.append(v)

        if not candidates:
            raise RegistryError("not_found", f"No version of '{name}' matches prefix '{ref}'.")

        candidates.sort()
        highest_version = candidates[-1]
        return versions_map[highest_version]

    def invoke(
        self,
        ref: str,
        args: Mapping[str, Any],
        *,
        granted: Collection[str],
    ) -> Any:
        """Invoke a tool after version resolution, permission verification and schema validation."""
        start_time = self._clock()
        name = ref.split("@")[0] if "@" in ref else ref
        version = "unknown"
        outcome = "ok"

        try:
            # 1. Resolve
            spec = self.resolve(ref)
            name = spec.name
            version = spec.version

            # 2. Permissions
            granted_set = set(granted)
            missing = tuple(sorted(spec.permissions - granted_set))
            if missing:
                outcome = "permission_denied"
                raise RegistryError(
                    "permission_denied",
                    f"Missing required permissions: {', '.join(missing)}",
                    missing=missing,
                )

            # 3. Validate arguments
            issues = validate(spec.input_schema, args)
            if issues:
                outcome = "invalid_args"
                raise RegistryError(
                    "invalid_args",
                    f"Argument validation failed with {len(issues)} issue(s).",
                    issues=tuple(issues),
                )

            # 4. Call fn
            try:
                result = spec.fn(**args)
                return result
            except Exception:
                outcome = "error"
                raise

        except RegistryError as exc:
            if exc.code == "not_found":
                outcome = "error"
            raise
        finally:
            duration_ms = (self._clock() - start_time) * 1000.0
            if self._on_event is not None:
                event_payload = {
                    "name": name,
                    "version": version,
                    "outcome": outcome,
                    "duration_ms": duration_ms,
                }
                self._on_event(event_payload)

    def list(self, *, granted: Collection[str] | None = None) -> builtins.list[ToolSpec]:
        """List latest version of each registered tool, sorted by name, filtered by grants."""
        granted_set = set(granted) if granted is not None else None
        result: list[ToolSpec] = []

        for name in sorted(self._tools.keys()):
            versions = self._tools[name]
            latest_ver = max(versions.keys())
            spec = versions[latest_ver]
            if granted_set is not None and not spec.permissions.issubset(granted_set):
                continue
            result.append(spec)

        return result

    def export(self, fmt: Literal["mcp", "json"] = "mcp") -> builtins.list[dict[str, Any]]:
        """Export latest tool specifications in MCP or extended JSON format."""
        if fmt not in ("mcp", "json"):
            raise ValueError(f"unknown export format: {fmt!r}")
        latest_specs = self.list()
        output: list[dict[str, Any]] = []
        for spec in latest_specs:
            if fmt == "mcp":
                output.append(
                    {
                        "name": spec.name,
                        "description": spec.description,
                        "inputSchema": dict(spec.input_schema),
                    }
                )
            elif fmt == "json":
                output.append(
                    {
                        "name": spec.name,
                        "version": spec.version,
                        "description": spec.description,
                        "inputSchema": dict(spec.input_schema),
                        "permissions": sorted(spec.permissions),
                    }
                )
            else:
                raise ValueError(f"Unsupported export format: {fmt}")
        return output
