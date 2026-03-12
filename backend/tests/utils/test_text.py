"""Tests for text utility functions."""

import pytest

from app.utils.text import standardize_text


class TestStandardizeText:
    """Tests for standardize_text function."""
    
    def test_standardize_text_empty_string(self):
        """Returns empty string for empty input."""
        assert standardize_text("") == ""
    
    def test_standardize_text_none(self):
        """Returns empty string for None input."""
        assert standardize_text(None) == ""
    
    def test_standardize_text_basic(self):
        """Normalizes basic text."""
        result = standardize_text("Hello  World")
        assert result == "Hello World"

    def test_standardize_text_normalizes_dashes(self):
        """Replaces various dash characters with a standard hyphen."""
        text = "a—b–c‐d"
        assert standardize_text(text) == "a-b-c-d"

    def test_standardize_text_normalizes_quotes(self):
        """Converts smart quotes to straight quotes."""
        text = "“Quoted” ‘text’"
        assert standardize_text(text) == '"Quoted" \'text\''

    def test_standardize_text_removes_soft_hyphen(self):
        """Strips soft hyphens from text."""
        text = "soft\u00adhyphen"
        assert standardize_text(text) == "softhyphen"

    def test_standardize_text_joins_hyphenated_line_breaks(self):
        """Removes hyphenation across line breaks."""
        text = "long-\n  word"
        assert standardize_text(text) == "longword"

    def test_standardize_text_trims_whitespace_and_newlines(self):
        """Strips leading/trailing spaces and collapses newlines."""
        text = "  spaced line\n\n\n\nnext  "
        assert standardize_text(text) == "spaced line\n\nnext"

    def test_standardize_text_removes_control_characters(self):
        """Removes control characters except newlines and tabs."""
        text = "a\x00b\x07c\n\t"
        # Note: trailing whitespace (including tabs) is stripped
        assert standardize_text(text) == "abc"
