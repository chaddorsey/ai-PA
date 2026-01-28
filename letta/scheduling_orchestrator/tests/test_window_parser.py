"""Tests for window parser."""
import pytest
from datetime import date, time


class TestParseTimePhrase:
    """Test parsing individual time phrases."""

    def test_anytime(self):
        """'anytime' parses to business hours."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("anytime")
        assert result["start"] == time(8, 0)
        assert result["end"] == time(18, 0)
        assert result["exclusions"] == []

    def test_until_time(self):
        """'until 4pm' parses to 8am-4pm."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("until 4pm")
        assert result["start"] == time(8, 0)
        assert result["end"] == time(16, 0)

    def test_after_time(self):
        """'after 1pm' parses to 1pm-6pm."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("after 1pm")
        assert result["start"] == time(13, 0)
        assert result["end"] == time(18, 0)

    def test_anytime_but(self):
        """'anytime but 3:30-4:30pm' excludes that range."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("anytime but 3:30-4:30pm")
        assert result["start"] == time(8, 0)
        assert result["end"] == time(18, 0)
        assert len(result["exclusions"]) == 1
        assert result["exclusions"][0]["start"] == time(15, 30)
        assert result["exclusions"][0]["end"] == time(16, 30)

    def test_between_times(self):
        """'between 10am and 2pm' parses correctly."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("between 10am and 2pm")
        assert result["start"] == time(10, 0)
        assert result["end"] == time(14, 0)

    def test_morning_only(self):
        """'morning only' parses to 8am-12pm."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("morning only")
        assert result["start"] == time(8, 0)
        assert result["end"] == time(12, 0)

    def test_afternoon(self):
        """'afternoon' parses to 12pm-6pm."""
        from scheduling_orchestrator.window_parser import parse_time_phrase

        result = parse_time_phrase("afternoon")
        assert result["start"] == time(12, 0)
        assert result["end"] == time(18, 0)
