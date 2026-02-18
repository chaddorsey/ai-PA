"""Tests for interval parser utility."""

from __future__ import annotations

import pytest

from gmail_watch.utils.interval_parser import (
    DEFAULT_FOLLOWUP_SECONDS,
    extract_interval_from_address,
    format_interval,
    parse_interval,
)


class TestParseInterval:
    """Tests for parse_interval function."""

    def test_hours(self):
        assert parse_interval("12h") == 43200

    def test_days(self):
        assert parse_interval("3d") == 259200

    def test_weeks(self):
        assert parse_interval("1w") == 604800

    def test_two_weeks(self):
        assert parse_interval("2w") == 1209600

    def test_whitespace_stripped(self):
        assert parse_interval("  3d  ") == 259200

    def test_uppercase(self):
        assert parse_interval("3D") == 259200

    def test_empty_returns_default(self):
        assert parse_interval("") == DEFAULT_FOLLOWUP_SECONDS

    def test_none_returns_default(self):
        assert parse_interval(None) == DEFAULT_FOLLOWUP_SECONDS

    def test_invalid_returns_default(self):
        assert parse_interval("abc") == DEFAULT_FOLLOWUP_SECONDS

    def test_no_unit_returns_default(self):
        assert parse_interval("3") == DEFAULT_FOLLOWUP_SECONDS


class TestFormatInterval:
    """Tests for format_interval function."""

    def test_one_week(self):
        assert format_interval(604800) == "1w"

    def test_three_days(self):
        assert format_interval(259200) == "3d"

    def test_twelve_hours(self):
        assert format_interval(43200) == "12h"

    def test_two_weeks(self):
        assert format_interval(1209600) == "2w"

    def test_one_day(self):
        assert format_interval(86400) == "1d"

    def test_non_round_days_uses_hours(self):
        assert format_interval(90000) == "25h"


class TestExtractIntervalFromAddress:
    """Tests for extract_interval_from_address function."""

    def test_three_days(self):
        result = extract_interval_from_address(
            "cdorsey+watch3d@concord.org", "cdorsey+watch"
        )
        assert result == 259200

    def test_twelve_hours(self):
        result = extract_interval_from_address(
            "cdorsey+watch12h@concord.org", "cdorsey+watch"
        )
        assert result == 43200

    def test_one_week(self):
        result = extract_interval_from_address(
            "cdorsey+watch1w@concord.org", "cdorsey+watch"
        )
        assert result == 604800

    def test_no_interval_returns_default(self):
        result = extract_interval_from_address(
            "cdorsey+watch@concord.org", "cdorsey+watch"
        )
        assert result == DEFAULT_FOLLOWUP_SECONDS

    def test_case_insensitive(self):
        result = extract_interval_from_address(
            "CDorsey+Watch3D@concord.org", "cdorsey+watch"
        )
        assert result == 259200

    def test_no_match_returns_none(self):
        result = extract_interval_from_address(
            "someone@example.com", "cdorsey+watch"
        )
        assert result is None
