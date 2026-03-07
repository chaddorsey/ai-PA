import json
from omnifocus_cli.bridge import build_payload, build_applescript


def test_build_payload_creates_correct_json():
    result = build_payload("getTask", {"taskId": "abc-123"})
    parsed = json.loads(result)
    assert parsed == {"method": "getTask", "params": {"taskId": "abc-123"}}


def test_build_payload_empty_params():
    result = build_payload("listTags", {})
    parsed = json.loads(result)
    assert parsed == {"method": "listTags", "params": {}}


def test_build_payload_defaults_params_to_empty():
    result = build_payload("listTags")
    parsed = json.loads(result)
    assert parsed == {"method": "listTags", "params": {}}


def test_build_applescript_contains_base64():
    script = build_applescript("listTags", {})
    assert 'tell application "OmniFocus"' in script
    assert "evaluate javascript" in script
    assert "PlugIn.find" in script
    assert "omnifocus-mcp" in script


def test_build_applescript_roundtrip_decode():
    import base64
    import re
    script = build_applescript("getTask", {"taskId": "test-id"})
    match = re.search(r"s='([A-Za-z0-9+/=]+)'", script)
    assert match, "Could not find base64 payload in script"
    decoded = base64.b64decode(match.group(1)).decode("utf-8")
    parsed = json.loads(decoded)
    assert parsed["method"] == "getTask"
    assert parsed["params"]["taskId"] == "test-id"
