"""Tests for time utility functions."""

import pytest

from app.utils.time import format_seconds


class TestFormatSeconds:
    """Tests for format_seconds function."""
    
    def test_format_seconds_basic(self):
        """Formats basic duration correctly."""
        assert format_seconds(90) == "1:30"
    
    def test_format_seconds_zero(self):
        """Handles zero seconds."""
        assert format_seconds(0) == "0:00"
    
    def test_format_seconds_less_than_minute(self):
        """Formats duration less than a minute."""
        assert format_seconds(45) == "0:45"
    
    def test_format_seconds_exact_minutes(self):
        """Formats exact minutes."""
        assert format_seconds(120) == "2:00"
    
    def test_format_seconds_large_duration(self):
        """Handles large durations."""
        assert format_seconds(3665) == "61:05"
    
    def test_format_seconds_with_decimals(self):
        """Handles float inputs by truncating."""
        assert format_seconds(90.7) == "1:30"
