"""Tests for the access whitelist module."""

from __future__ import annotations

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


class TestWhitelistInactive:
    """When whitelist is not active, all emails should be allowed."""

    def test_all_emails_allowed_by_default(self):
        assert whitelist.is_email_allowed("anyone@example.com") is True

    def test_load_whitelist_sets_inactive(self):
        whitelist.load_whitelist()
        assert whitelist._whitelist_active is False
        assert whitelist.is_email_allowed("anyone@example.com") is True


class TestWhitelistActive:
    """When whitelist is active with cached emails."""

    def test_allowed_email(self):
        whitelist._allowed_emails = {"alice@example.com", "bob@example.com"}
        whitelist._whitelist_active = True

        assert whitelist.is_email_allowed("alice@example.com") is True
        assert whitelist.is_email_allowed("bob@example.com") is True

    def test_denied_email(self):
        whitelist._allowed_emails = {"alice@example.com"}
        whitelist._whitelist_active = True

        assert whitelist.is_email_allowed("eve@example.com") is False

    def test_case_insensitive(self):
        whitelist._allowed_emails = {"alice@example.com"}
        whitelist._whitelist_active = True

        assert whitelist.is_email_allowed("Alice@Example.COM") is True
        assert whitelist.is_email_allowed("ALICE@EXAMPLE.COM") is True

    def test_whitespace_stripped(self):
        whitelist._allowed_emails = {"alice@example.com"}
        whitelist._whitelist_active = True

        assert whitelist.is_email_allowed("  alice@example.com  ") is True

    def test_empty_whitelist_denies_all(self):
        whitelist._allowed_emails = set()
        whitelist._whitelist_active = True

        assert whitelist.is_email_allowed("anyone@example.com") is False
