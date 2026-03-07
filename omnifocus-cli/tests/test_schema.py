import pytest
from omnifocus_cli.schema import SCHEMAS, get_schema, list_schemas


def test_get_schema_returns_task_create():
    s = get_schema("task.create")
    assert s["method"] == "createTask"
    assert "name" in s["params"]
    assert s["params"]["name"]["required"] is True


def test_get_schema_returns_none_for_unknown():
    assert get_schema("bogus.method") is None


def test_list_schemas_returns_all_keys():
    keys = list_schemas()
    assert "task.create" in keys
    assert "task.get" in keys
    assert "task.update" in keys
    assert "task.complete" in keys
    assert "task.delete" in keys
    assert "task.move" in keys
    assert "task.list" in keys
    assert "search" in keys
    assert "project.list" in keys
    assert "project.get" in keys
    assert "project.create" in keys
    assert "project.update" in keys
    assert "folder.list" in keys
    assert "inbox.list" in keys
    assert "inbox.process" in keys
    assert "tags.list" in keys
    assert "tags.create" in keys
    assert "tags.rename" in keys
    assert "tags.delete" in keys


def test_all_schemas_have_method_and_params():
    for key in list_schemas():
        s = get_schema(key)
        assert "method" in s, f"{key} missing 'method'"
        assert "params" in s, f"{key} missing 'params'"
        assert isinstance(s["params"], dict), f"{key} params not a dict"


def test_param_entries_have_required_fields():
    for key in list_schemas():
        s = get_schema(key)
        for pname, pdef in s["params"].items():
            assert "type" in pdef, f"{key}.{pname} missing 'type'"
            assert "required" in pdef, f"{key}.{pname} missing 'required'"
            assert "description" in pdef, f"{key}.{pname} missing 'description'"
