"""Tests for bouwmeester.core.query_utils."""

from bouwmeester.core.query_utils import escape_like, normalize_email


class TestNormalizeEmail:
    def test_strips_whitespace(self):
        assert normalize_email("  user@example.com  ") == "user@example.com"

    def test_lowercases(self):
        assert normalize_email("User@Example.COM") == "user@example.com"

    def test_strips_and_lowercases(self):
        assert normalize_email("  Jan@BZK.NL  ") == "jan@bzk.nl"

    def test_already_normalized(self):
        assert normalize_email("user@example.com") == "user@example.com"

    def test_empty_string(self):
        assert normalize_email("") == ""


class TestEscapeLike:
    def test_escapes_percent(self):
        assert escape_like("100%") == "100\\%"

    def test_escapes_underscore(self):
        assert escape_like("a_b") == "a\\_b"

    def test_escapes_backslash(self):
        assert escape_like("a\\b") == "a\\\\b"

    def test_escapes_all_special_chars(self):
        assert escape_like("a\\b%c_d") == "a\\\\b\\%c\\_d"

    def test_no_special_chars(self):
        assert escape_like("hello world") == "hello world"

    def test_empty_string(self):
        assert escape_like("") == ""
