"""Comprehensive tests for tool_registry package."""

import pytest

from tool_registry import Issue, Registry, RegistryError, ToolSpec, validate


def dummy_fn(**kwargs: object) -> str:
    return "success"


def test_acceptance_semver_resolution() -> None:
    """After registering read_file 1.0.0, 1.2.0 and 2.0.0, resolve('read_file') returns 2.0.0,
    resolve('read_file@1') returns 1.2.0, resolve('read_file@1.0') returns 1.0.0 and
    resolve('read_file@3') raises RegistryError with code 'not_found'."""
    reg = Registry()
    schema = {"type": "object"}
    spec_1_0_0 = ToolSpec("read_file", "1.0.0", "desc 1.0.0", schema, frozenset(), dummy_fn)
    spec_1_2_0 = ToolSpec("read_file", "1.2.0", "desc 1.2.0", schema, frozenset(), dummy_fn)
    spec_2_0_0 = ToolSpec("read_file", "2.0.0", "desc 2.0.0", schema, frozenset(), dummy_fn)

    reg.register(spec_1_0_0)
    reg.register(spec_1_2_0)
    reg.register(spec_2_0_0)

    assert reg.resolve("read_file").version == "2.0.0"
    assert reg.resolve("read_file@1").version == "1.2.0"
    assert reg.resolve("read_file@1.0").version == "1.0.0"
    with pytest.raises(RegistryError) as exc_info:
        reg.resolve("read_file@3")
    assert exc_info.value.code == "not_found"


def test_acceptance_permissions_enforcement() -> None:
    """For a tool with permissions {'fs.read'}, invoke('read_file', args, granted=set())
    raises RegistryError with code 'permission_denied' and .missing == ('fs.read,') without calling fn,
    granted={'fs.read'} returns fn's result, and list(granted=set()) omits the tool."""
    reg = Registry()
    called = []

    def target_fn(**kwargs: object) -> str:
        called.append(True)
        return "content"

    spec = ToolSpec(
        "read_file",
        "1.0.0",
        "read a file",
        {"type": "object"},
        frozenset({"fs.read"}),
        target_fn,
    )
    reg.register(spec)

    # invoke with empty granted
    with pytest.raises(RegistryError) as exc_info:
        reg.invoke("read_file", {}, granted=set())
    assert exc_info.value.code == "permission_denied"
    assert exc_info.value.missing == ("fs.read",)
    assert len(called) == 0

    # invoke with granted
    res = reg.invoke("read_file", {}, granted={"fs.read"})
    assert res == "content"
    assert len(called) == 1

    # list(granted=set()) omits tool
    assert reg.list(granted=set()) == []
    assert len(reg.list(granted={"fs.read"})) == 1


def test_acceptance_schema_validation() -> None:
    """For schema {'type': 'object', 'properties': {'path': {'type': 'string', 'maxLength': 5}},
    'required': ['path'], 'additionalProperties': False},
    validate(schema, {'path': 'abcdef', 'x': 1}) == [Issue('/path', 'maxLength'), Issue('/x', 'additionalProperties')]
    and validate(schema, {}) == [Issue('/path', 'required')]."""
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "maxLength": 5}},
        "required": ["path"],
        "additionalProperties": False,
    }
    issues1 = validate(schema, {"path": "abcdef", "x": 1})
    assert issues1 == [Issue("/path", "maxLength"), Issue("/x", "additionalProperties")]

    issues2 = validate(schema, {})
    assert issues2 == [Issue("/path", "required")]


def test_acceptance_type_rules() -> None:
    """True is invalid for {'type': 'integer'} and {'type': 'number'},
    1.0 is valid for {'type': 'integer'}, and 1.5 is invalid for it."""
    int_schema = {"type": "object", "properties": {"val": {"type": "integer"}}}
    num_schema = {"type": "object", "properties": {"val": {"type": "number"}}}

    # True is invalid for integer and number
    assert validate(int_schema, {"val": True}) == [Issue("/val", "type")]
    assert validate(num_schema, {"val": True}) == [Issue("/val", "type")]

    # 1.0 is valid for integer
    assert validate(int_schema, {"val": 1.0}) == []

    # 1.5 is invalid for integer
    assert validate(int_schema, {"val": 1.5}) == [Issue("/val", "type")]


def test_acceptance_invoke_invalid_args() -> None:
    """invoke with arguments that fail validation raises RegistryError with code 'invalid_args'
    carrying .issues, and fn is not called."""
    called = []

    def fn(**kwargs: object) -> str:
        called.append(True)
        return "ok"

    spec = ToolSpec(
        "write_file",
        "1.0.0",
        "write file",
        {"type": "object", "required": ["path"], "properties": {"path": {"type": "string"}}},
        frozenset(),
        fn,
    )
    reg = Registry()
    reg.register(spec)

    with pytest.raises(RegistryError) as exc_info:
        reg.invoke("write_file", {}, granted=set())
    assert exc_info.value.code == "invalid_args"
    assert exc_info.value.issues == (Issue("/path", "required"),)
    assert len(called) == 0


def test_acceptance_registration_constraints() -> None:
    """Registering the same name and version twice raises 'duplicate_version',
    the name 'Read File' raises 'invalid_name', version '1.2' raises 'invalid_version',
    a schema using 'oneOf' raises 'invalid_schema' and a schema nested 33 levels deep raises 'invalid_schema'."""
    reg = Registry()
    valid_spec = ToolSpec("my_tool", "1.0.0", "desc", {"type": "object"}, frozenset(), dummy_fn)
    reg.register(valid_spec)

    # Duplicate version
    with pytest.raises(RegistryError) as exc_dup:
        reg.register(valid_spec)
    assert exc_dup.value.code == "duplicate_version"

    # Invalid name
    with pytest.raises(RegistryError) as exc_name:
        reg.register(
            ToolSpec("Read File", "1.0.0", "desc", {"type": "object"}, frozenset(), dummy_fn)
        )
    assert exc_name.value.code == "invalid_name"

    # Invalid version
    with pytest.raises(RegistryError) as exc_ver:
        reg.register(
            ToolSpec("my_tool_2", "1.2", "desc", {"type": "object"}, frozenset(), dummy_fn)
        )
    assert exc_ver.value.code == "invalid_version"

    # Schema using oneOf
    with pytest.raises(RegistryError) as exc_schema:
        reg.register(
            ToolSpec(
                "my_tool_3", "1.0.0", "desc", {"type": "object", "oneOf": []}, frozenset(), dummy_fn
            )
        )
    assert exc_schema.value.code == "invalid_schema"

    # Schema nested 33 levels deep
    nested: dict[str, object] = {"type": "string"}
    for _ in range(32):
        nested = {"type": "object", "properties": {"child": nested}}
    # nested is at depth 33
    with pytest.raises(RegistryError) as exc_depth:
        reg.register(ToolSpec("my_tool_deep", "1.0.0", "desc", nested, frozenset(), dummy_fn))
    assert exc_depth.value.code == "invalid_schema"


def test_acceptance_export() -> None:
    """export('mcp') returns [{'name': 'read_file', 'description': ..., 'inputSchema': {...}}]
    for the latest version of each tool sorted by name, and export('json') adds 'version' and a sorted 'permissions' list."""
    reg = Registry()
    reg.register(
        ToolSpec(
            "read_file",
            "1.0.0",
            "read file old",
            {"type": "object"},
            frozenset({"fs.read"}),
            dummy_fn,
        )
    )
    reg.register(
        ToolSpec(
            "read_file",
            "2.0.0",
            "read file new",
            {"type": "object"},
            frozenset({"fs.read", "fs.audit"}),
            dummy_fn,
        )
    )
    reg.register(
        ToolSpec(
            "audit_log",
            "1.0.0",
            "audit log",
            {"type": "object"},
            frozenset(),
            dummy_fn,
        )
    )

    mcp_export = reg.export("mcp")
    assert len(mcp_export) == 2
    # Sorted by name: audit_log then read_file
    assert mcp_export[0] == {
        "name": "audit_log",
        "description": "audit log",
        "inputSchema": {"type": "object"},
    }
    assert mcp_export[1] == {
        "name": "read_file",
        "description": "read file new",
        "inputSchema": {"type": "object"},
    }

    json_export = reg.export("json")
    assert len(json_export) == 2
    assert json_export[0] == {
        "name": "audit_log",
        "version": "1.0.0",
        "description": "audit log",
        "inputSchema": {"type": "object"},
        "permissions": [],
    }
    assert json_export[1] == {
        "name": "read_file",
        "version": "2.0.0",
        "description": "read file new",
        "inputSchema": {"type": "object"},
        "permissions": ["fs.audit", "fs.read"],
    }


def test_acceptance_capacity_and_telemetry() -> None:
    """The 1_001st registration raises 'too_many_tools', and on_event payloads for invoke
    contain name, version, outcome and duration_ms but never the sentinel 'SENTINEL-tr5' passed in the arguments."""
    events: list[dict[str, object]] = []
    reg = Registry(max_tools=10, on_event=events.append)

    for i in range(10):
        reg.register(
            ToolSpec(f"tool_{i}", "1.0.0", f"Tool {i}", {"type": "object"}, frozenset(), dummy_fn)
        )

    with pytest.raises(RegistryError) as exc_cap:
        reg.register(
            ToolSpec("tool_11", "1.0.0", "Tool 11", {"type": "object"}, frozenset(), dummy_fn)
        )
    assert exc_cap.value.code == "too_many_tools"

    # Test telemetry payload without leaking arguments (a fresh registry: the first one is full)
    reg = Registry(max_tools=10, on_event=events.append)
    reg.register(
        ToolSpec(
            "audit_tool",
            "1.0.0",
            "audit",
            {"type": "object", "properties": {"secret": {"type": "string"}}},
            frozenset(),
            dummy_fn,
        )
    )
    sentinel = "SENTINEL-tr5"
    reg.invoke("audit_tool", {"secret": sentinel}, granted=set())

    assert len(events) == 1
    ev = events[0]
    assert ev["name"] == "audit_tool"
    assert ev["version"] == "1.0.0"
    assert ev["outcome"] == "ok"
    assert isinstance(ev["duration_ms"], float)
    assert sentinel not in str(ev)


def test_edge_cases_and_coverage() -> None:
    """Test edge cases: empty registry list, zero permissions, enum mixed types,
    nested arrays/objects, RFC 6901 escaping, custom clock, error outcome event."""
    # Empty registry list
    reg = Registry()
    assert reg.list() == []

    # Tool with no permissions is always allowed
    reg.register(
        ToolSpec("free_tool", "1.0.0", "desc", {"type": "object"}, frozenset(), lambda: 42)
    )
    assert reg.invoke("free_tool", {}, granted=set()) == 42

    # Enum with mixed types
    schema_enum = {"type": "object", "properties": {"mixed": {"enum": ["a", 1, True, None]}}}
    assert validate(schema_enum, {"mixed": "a"}) == []
    assert validate(schema_enum, {"mixed": 1}) == []
    assert validate(schema_enum, {"mixed": True}) == []
    assert validate(schema_enum, {"mixed": None}) == []
    assert validate(schema_enum, {"mixed": False}) == [Issue("/mixed", "enum")]
    assert validate(schema_enum, {"mixed": 2}) == [Issue("/mixed", "enum")]

    # RFC 6901 escaping with / and ~
    schema_escaping = {
        "type": "object",
        "properties": {"a/b~c": {"type": "string", "minLength": 3}},
    }
    issues = validate(schema_escaping, {"a/b~c": "x"})
    assert issues == [Issue("/a~1b~0c", "minLength")]

    # Nested array of objects
    nested_schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer"}},
                },
            }
        },
    }
    assert validate(nested_schema, {"items": [{"id": 1}, {"id": 2}]}) == []
    bad_res = validate(nested_schema, {"items": [{"id": "not_int"}, {}]})
    assert bad_res == [Issue("/items/0/id", "type"), Issue("/items/1/id", "required")]

    # Injected clock and error outcome propagation
    clock_time = 100.0
    events = []

    def fake_clock() -> float:
        nonlocal clock_time
        clock_time += 0.05
        return clock_time

    def failing_fn() -> None:
        raise RuntimeError("boom")

    reg_telemetry = Registry(clock=fake_clock, on_event=events.append)
    reg_telemetry.register(
        ToolSpec("fail_tool", "1.0.0", "fails", {"type": "object"}, frozenset(), failing_fn)
    )

    with pytest.raises(RuntimeError, match="boom"):
        reg_telemetry.invoke("fail_tool", {}, granted=set())

    assert len(events) == 1
    assert events[0]["outcome"] == "error"
    assert events[0]["duration_ms"] > 0

    # Resolve unknown ref raises not_found
    with pytest.raises(RegistryError) as exc_res:
        reg_telemetry.invoke("nonexistent", {}, granted=set())
    assert exc_res.value.code == "not_found"
    assert len(events) == 2
    assert events[1]["outcome"] == "error"


def test_error_and_edge_paths() -> None:
    """Exercise error branches for complete coverage."""
    # Invalid ref format
    reg = Registry()
    with pytest.raises(RegistryError) as exc1:
        reg.resolve("bad_tool@1.2.3.4")
    assert exc1.value.code == "invalid_version"

    with pytest.raises(RegistryError) as exc_p:
        reg.resolve("bad_tool@1.02")
    assert exc_p.value.code == "invalid_version"

    with pytest.raises(RegistryError) as exc2:
        reg.resolve("BadToolName")
    assert exc2.value.code == "invalid_name"

    # Invalid export format
    with pytest.raises(ValueError):
        reg.export("invalid_fmt")  # type: ignore[arg-type]

    # Invalid permission pattern
    with pytest.raises(RegistryError) as exc3:
        reg.register(
            ToolSpec(
                "tool_invalid_perm",
                "1.0.0",
                "",
                {"type": "object"},
                frozenset({"INVALID_PERM"}),
                dummy_fn,
            )
        )
    assert exc3.value.code == "invalid_schema"

    # Non-object root schema
    with pytest.raises(RegistryError) as exc4:
        reg.register(
            ToolSpec("tool_str_root", "1.0.0", "", {"type": "string"}, frozenset(), dummy_fn)
        )
    assert exc4.value.code == "invalid_schema"

    # Minimum and Maximum checks
    num_bounds = {
        "type": "object",
        "properties": {"count": {"type": "integer", "minimum": 10, "maximum": 20}},
    }
    assert validate(num_bounds, {"count": 9}) == [Issue("/count", "minimum")]
    assert validate(num_bounds, {"count": 21}) == [Issue("/count", "maximum")]
    assert validate(num_bounds, {"count": 15}) == []

    # Allowed annotations (title, description, default)
    annotated = {
        "type": "object",
        "title": "Config",
        "description": "Configuration schema",
        "properties": {"name": {"type": "string", "default": "anon"}},
    }
    assert validate(annotated, {"name": "user"}) == []
