import pytest
from omnifocus_cli.validate import validate_body, validate_uuid, validate_date, validate_name


class TestValidateBody:
    def test_valid_body_passes(self):
        errors = validate_body("task.create", {"name": "Buy milk"})
        assert errors == []

    def test_missing_required_field(self):
        errors = validate_body("task.create", {})
        assert any(e["field"] == "name" and "required" in e["error"] for e in errors)

    def test_unknown_field_rejected(self):
        errors = validate_body("task.create", {"name": "X", "bogusField": 1})
        assert any(e["field"] == "bogusField" and "unknown" in e["error"] for e in errors)

    def test_type_mismatch_boolean(self):
        errors = validate_body("task.create", {"name": "X", "flagged": "yes"})
        assert any(e["field"] == "flagged" and "boolean" in e["error"] for e in errors)

    def test_type_mismatch_integer(self):
        errors = validate_body("task.create", {"name": "X", "estimatedMinutes": "thirty"})
        assert any(e["field"] == "estimatedMinutes" and "integer" in e["error"] for e in errors)

    def test_type_mismatch_array(self):
        errors = validate_body("task.create", {"name": "X", "tagIds": "not-an-array"})
        assert any(e["field"] == "tagIds" and "array" in e["error"] for e in errors)

    def test_multiple_errors_returned(self):
        errors = validate_body("task.create", {"flagged": "yes", "bogus": 1})
        assert len(errors) >= 3

    def test_unknown_schema_key(self):
        errors = validate_body("bogus.method", {"name": "X"})
        assert any("unknown" in e["error"].lower() or "schema" in e["error"].lower() for e in errors)

    def test_optional_fields_not_required(self):
        errors = validate_body("task.create", {"name": "Buy milk"})
        assert errors == []

    def test_integer_not_confused_with_boolean(self):
        """True/False should fail integer validation, 42 should pass."""
        errors = validate_body("task.create", {"name": "X", "estimatedMinutes": True})
        assert any(e["field"] == "estimatedMinutes" for e in errors)

    def test_valid_array_string(self):
        errors = validate_body("task.create", {"name": "X", "tagIds": ["tag-1", "tag-2"]})
        assert errors == []

    def test_object_type(self):
        errors = validate_body("project.update", {"projectId": "p-1", "properties": {"name": "New"}})
        assert errors == []

    def test_object_type_mismatch(self):
        errors = validate_body("project.update", {"projectId": "p-1", "properties": "not-an-object"})
        assert any(e["field"] == "properties" for e in errors)


class TestValidateUuid:
    def test_valid_uuid(self):
        assert validate_uuid("abc-123-def") is None

    def test_rejects_question_mark(self):
        assert validate_uuid("abc?123") is not None

    def test_rejects_hash(self):
        assert validate_uuid("abc#123") is not None

    def test_rejects_percent(self):
        assert validate_uuid("abc%123") is not None

    def test_rejects_dot_dot(self):
        assert validate_uuid("abc..123") is not None

    def test_rejects_control_chars(self):
        assert validate_uuid("abc\x00123") is not None
        assert validate_uuid("abc\x1f123") is not None
        assert validate_uuid("abc\x7f123") is not None

    def test_rejects_whitespace(self):
        assert validate_uuid("abc 123") is not None
        assert validate_uuid("abc\t123") is not None
        assert validate_uuid("abc\n123") is not None

    def test_rejects_empty(self):
        assert validate_uuid("") is not None


class TestValidateDate:
    def test_valid_date(self):
        assert validate_date("2026-03-10") is None

    def test_valid_datetime(self):
        assert validate_date("2026-03-10T17:00:00Z") is None

    def test_valid_datetime_with_offset(self):
        assert validate_date("2026-03-10T17:00:00+05:00") is None

    def test_invalid_date(self):
        assert validate_date("not-a-date") is not None

    def test_invalid_format(self):
        assert validate_date("03/10/2026") is not None

    def test_empty_string(self):
        assert validate_date("") is not None


class TestValidateName:
    def test_valid_name(self):
        assert validate_name("Buy milk") is None

    def test_allows_slashes(self):
        assert validate_name("Work / Personal") is None

    def test_allows_hyphens_dashes(self):
        assert validate_name("High-priority -- urgent") is None

    def test_allows_unicode(self):
        assert validate_name("Reunion con Jose") is None

    def test_rejects_control_chars(self):
        assert validate_name("Bad\x00name") is not None
        assert validate_name("Bad\x1fname") is not None
        assert validate_name("Bad\x7fname") is not None

    def test_rejects_empty(self):
        assert validate_name("") is not None
