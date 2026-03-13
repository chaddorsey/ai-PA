"""Tests for the NotebookLM CLI schema registry."""

from __future__ import annotations


def test_list_schemas_returns_all():
    """list_schemas() returns at least 35 keys covering all groups."""
    from notebooklm_cli.schema import list_schemas

    keys = list_schemas()
    assert len(keys) >= 35

    # Sample entries from each group
    for expected in [
        "notebook.create",
        "notebook.list",
        "notebook.delete",
        "source.add-url",
        "source.add-text",
        "source.add-file",
        "source.list",
        "artifact.generate",
        "artifact.list",
        "artifact.download",
        "chat.ask",
        "chat.history",
        "research.start",
        "research.poll",
        "note.create",
        "note.list",
    ]:
        assert expected in keys, f"Missing expected key: {expected}"


def test_get_schema_returns_method():
    """get_schema('notebook.create') has method='create' and title is required."""
    from notebooklm_cli.schema import get_schema

    schema = get_schema("notebook.create")
    assert schema is not None
    assert schema["method"] == "create"
    assert "title" in schema["params"]
    assert schema["params"]["title"]["required"] is True


def test_get_schema_unknown():
    """get_schema with a bogus key returns None."""
    from notebooklm_cli.schema import get_schema

    assert get_schema("bogus.key") is None
    assert get_schema("") is None
    assert get_schema("notebook.bogus") is None


def test_all_schemas_have_method():
    """Every schema entry has method, description, and params keys."""
    from notebooklm_cli.schema import SCHEMAS

    for key, schema in SCHEMAS.items():
        assert "method" in schema, f"{key}: missing 'method'"
        assert "description" in schema, f"{key}: missing 'description'"
        assert "params" in schema, f"{key}: missing 'params'"
        assert isinstance(schema["method"], str), f"{key}: method must be a string"
        assert isinstance(schema["description"], str), f"{key}: description must be a string"
        assert isinstance(schema["params"], dict), f"{key}: params must be a dict"
