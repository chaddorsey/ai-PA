from slack_cli.schema import get_schema, list_schemas, list_groups, get_group_methods


def test_get_schema_exists():
    schema = get_schema("chat.postMessage")
    assert schema is not None
    assert schema["method"] == "chat.postMessage"
    assert "channel" in schema["params"]


def test_get_schema_not_found():
    assert get_schema("bogus.method") is None


def test_list_schemas():
    schemas = list_schemas()
    assert len(schemas) > 40
    assert "chat.postMessage" in schemas
    assert "conversations.list" in schemas
    assert "search.messages" in schemas


def test_list_groups():
    groups = list_groups()
    assert "chat" in groups
    assert "conversations" in groups
    assert "users" in groups
    assert "search" in groups
    assert "files" in groups
    assert "reactions" in groups
    assert "pins" in groups
    assert "bookmarks" in groups
    assert "reminders" in groups
    assert "team" in groups


def test_schema_has_token_type():
    schema = get_schema("chat.postMessage")
    assert schema["token_type"] in ("bot", "user", "either")


def test_search_requires_user_token():
    schema = get_schema("search.messages")
    assert schema["token_type"] == "user"


def test_get_group_methods():
    methods = get_group_methods("conversations")
    assert len(methods) >= 16
    assert "conversations.list" in methods
    assert "conversations.history" in methods


def test_conversations_history_has_semantic_types():
    schema = get_schema("conversations.history")
    assert schema["params"]["channel"].get("semantic_type") == "slack_id"
    assert schema["params"]["oldest"].get("semantic_type") == "timestamp"


def test_all_schemas_have_required_fields():
    for method_name in list_schemas():
        schema = get_schema(method_name)
        assert "method" in schema, f"{method_name} missing 'method'"
        assert "description" in schema, f"{method_name} missing 'description'"
        assert "token_type" in schema, f"{method_name} missing 'token_type'"
        assert "params" in schema, f"{method_name} missing 'params'"
        assert schema["token_type"] in ("bot", "user", "either"), f"{method_name} bad token_type"
