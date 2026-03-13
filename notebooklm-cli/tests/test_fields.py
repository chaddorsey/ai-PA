from __future__ import annotations

from notebooklm_cli.fields import apply_field_mask


def test_mask_dict():
    data = {"id": "1", "title": "Test", "extra": "x"}
    assert apply_field_mask(data, ["id", "title"]) == {"id": "1", "title": "Test"}


def test_mask_list():
    data = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
    result = apply_field_mask(data, ["id"])
    assert result == [{"id": "1"}, {"id": "2"}]


def test_mask_none_passthrough():
    data = {"id": "1", "title": "Test"}
    assert apply_field_mask(data, None) == data
