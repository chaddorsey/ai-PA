from slack_cli.validate import validate_slack_id, validate_timestamp, validate_body, sanitize_value


VALID_CHANNEL_IDS = ["C0123ABCDEF", "C012345678", "C0123456789AB"]
VALID_USER_IDS = ["U0123ABCDEF", "U012345678"]
VALID_DM_IDS = ["D0123ABCDEF"]
VALID_GROUP_IDS = ["G0123ABCDEF"]
VALID_TIMESTAMPS = ["1234567890.123456", "1709000000.000001"]


def test_valid_channel_ids():
    for cid in VALID_CHANNEL_IDS:
        assert validate_slack_id(cid) is None, f"Should accept {cid}"


def test_valid_user_ids():
    for uid in VALID_USER_IDS:
        assert validate_slack_id(uid) is None, f"Should accept {uid}"


def test_valid_dm_and_group_ids():
    for did in VALID_DM_IDS + VALID_GROUP_IDS:
        assert validate_slack_id(did) is None, f"Should accept {did}"


def test_reject_query_params_in_id():
    assert validate_slack_id("C0123ABCD?foo=bar") is not None


def test_reject_fragment_in_id():
    assert validate_slack_id("U0123ABCD#section") is not None


def test_reject_encoded_chars_in_id():
    assert validate_slack_id("C%200123ABCD") is not None


def test_reject_control_chars_in_id():
    assert validate_slack_id("C0123\x00ABCD") is not None


def test_reject_empty_id():
    assert validate_slack_id("") is not None


def test_reject_bad_prefix():
    assert validate_slack_id("X0123ABCDEF") is not None


def test_valid_timestamps():
    for ts in VALID_TIMESTAMPS:
        assert validate_timestamp(ts) is None, f"Should accept {ts}"


def test_reject_bad_timestamp():
    assert validate_timestamp("not-a-timestamp") is not None
    assert validate_timestamp("1234567890") is not None
    assert validate_timestamp("") is not None


def test_sanitize_value_strips_control():
    assert sanitize_value("hello\x00world") is not None


def test_sanitize_value_allows_newlines():
    assert sanitize_value("hello\nworld", allow_newlines=True) is None


def test_validate_body_missing_required():
    schema_params = {
        "channel": {"type": "string", "required": True},
        "text": {"type": "string", "required": True},
    }
    errors = validate_body({"channel": "C123"}, schema_params)
    assert len(errors) == 1
    assert errors[0]["field"] == "text"


def test_validate_body_unknown_field():
    schema_params = {
        "channel": {"type": "string", "required": True},
    }
    errors = validate_body({"channel": "C123", "bogus": "val"}, schema_params)
    assert len(errors) == 1
    assert "unknown" in errors[0]["error"].lower()
