"""Tests for the access whitelist module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from bouwmeester.core import whitelist


@pytest.fixture(autouse=True)
def _reset_whitelist():
    """Reset module-level cache before and after each test."""
    whitelist._allowed_emails = None
    whitelist._whitelist_active = False
    yield
    whitelist._allowed_emails = None
    whitelist._whitelist_active = False


class TestNoWhitelistFile:
    """When no whitelist file exists, all emails should be allowed."""

    def test_all_emails_allowed(self):
        with (
            patch.object(whitelist, "_JSON_PATH", Path("/nonexistent/wl.json")),
            patch.object(whitelist, "_AGE_PATH", Path("/nonexistent/wl.json.age")),
        ):
            whitelist.load_whitelist()

        assert whitelist.is_email_allowed("anyone@example.com") is True

    def test_whitelist_not_active(self):
        with (
            patch.object(whitelist, "_JSON_PATH", Path("/nonexistent/wl.json")),
            patch.object(whitelist, "_AGE_PATH", Path("/nonexistent/wl.json.age")),
        ):
            whitelist.load_whitelist()

        assert whitelist._whitelist_active is False


class TestWhitelistLoaded:
    """When a whitelist JSON file is present."""

    def test_allowed_email(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"emails": ["alice@example.com", "bob@example.com"]}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist.is_email_allowed("alice@example.com") is True
        assert whitelist.is_email_allowed("bob@example.com") is True

    def test_denied_email(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"emails": ["alice@example.com"]}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist.is_email_allowed("eve@example.com") is False

    def test_case_insensitive(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"emails": ["Alice@Example.COM"]}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist.is_email_allowed("alice@example.com") is True
        assert whitelist.is_email_allowed("ALICE@EXAMPLE.COM") is True
        assert whitelist.is_email_allowed("Alice@Example.COM") is True

    def test_whitespace_stripped(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"emails": ["  alice@example.com  "]}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist.is_email_allowed("alice@example.com") is True
        assert whitelist.is_email_allowed("  alice@example.com  ") is True

    def test_empty_whitelist_denies_all(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"emails": []}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist._whitelist_active is True
        assert whitelist.is_email_allowed("anyone@example.com") is False


class TestMalformedWhitelist:
    """Malformed files should fail-closed (deny all)."""

    def test_invalid_json_denies_all(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text("not valid json {{{")

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist._whitelist_active is True
        assert whitelist.is_email_allowed("anyone@example.com") is False

    def test_missing_emails_key_allows_none(self, tmp_path: Path):
        wl = tmp_path / "access_whitelist.json"
        wl.write_text(json.dumps({"wrong_key": ["a@b.com"]}))

        with patch.object(whitelist, "_JSON_PATH", wl):
            whitelist.load_whitelist()

        assert whitelist._whitelist_active is True
        assert whitelist.is_email_allowed("a@b.com") is False
