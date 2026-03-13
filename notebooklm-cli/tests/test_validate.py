from __future__ import annotations

from notebooklm_cli.validate import validate_body, validate_path


def test_validate_body_required_field():
    errors = validate_body("notebook.create", {})
    assert any(e["field"] == "title" for e in errors)


def test_validate_body_valid():
    errors = validate_body("notebook.create", {"title": "Test"})
    assert errors == []


def test_validate_body_unknown_field():
    errors = validate_body("notebook.create", {"title": "Test", "bogus": "x"})
    assert any(e["field"] == "bogus" for e in errors)


def test_validate_body_type_check():
    errors = validate_body("notebook.create", {"title": 123})
    assert any(e["field"] == "title" for e in errors)


def test_validate_path_rejects_traversal():
    err = validate_path("../../etc/passwd")
    assert err is not None
    assert ".." in err


def test_validate_path_allows_normal():
    err = validate_path("/Users/test/file.pdf")
    assert err is None
