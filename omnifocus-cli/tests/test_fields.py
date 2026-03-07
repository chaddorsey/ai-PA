from omnifocus_cli.fields import apply_field_mask


def test_filters_dict():
    data = {"id": "t-1", "name": "Buy milk", "flagged": True, "note": "long text"}
    result = apply_field_mask(data, ["id", "name", "flagged"])
    assert result == {"id": "t-1", "name": "Buy milk", "flagged": True}


def test_filters_list_of_dicts():
    data = [
        {"id": "t-1", "name": "A", "note": "x"},
        {"id": "t-2", "name": "B", "note": "y"},
    ]
    result = apply_field_mask(data, ["id", "name"])
    assert result == [{"id": "t-1", "name": "A"}, {"id": "t-2", "name": "B"}]


def test_unknown_fields_ignored_gracefully():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, ["id", "name", "nonexistent"])
    assert result == {"id": "t-1", "name": "A"}


def test_none_fields_returns_data_unchanged():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, None)
    assert result == data


def test_empty_fields_returns_empty_dicts():
    data = {"id": "t-1", "name": "A"}
    result = apply_field_mask(data, [])
    assert result == {}


def test_non_dict_data_returned_as_is():
    assert apply_field_mask("raw string", ["id"]) == "raw string"
    assert apply_field_mask(42, ["id"]) == 42
