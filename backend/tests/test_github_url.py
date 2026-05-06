"""Tests voor de GitHub URL-parser."""

import pytest

from bouwmeester.core.github_url import GitHubLinkType, parse_github_url


@pytest.mark.parametrize(
    "url,expected_type,owner,repo,ref",
    [
        (
            "https://github.com/anneschuth/regelrecht-upload",
            GitHubLinkType.repo,
            "anneschuth",
            "regelrecht-upload",
            None,
        ),
        (
            "https://github.com/anneschuth/regelrecht-upload/",
            GitHubLinkType.repo,
            "anneschuth",
            "regelrecht-upload",
            None,
        ),
        (
            "https://www.github.com/anneschuth/regelrecht-upload",
            GitHubLinkType.repo,
            "anneschuth",
            "regelrecht-upload",
            None,
        ),
        (
            "https://github.com/anneschuth/regelrecht-upload.git",
            GitHubLinkType.repo,
            "anneschuth",
            "regelrecht-upload",
            None,
        ),
        (
            "https://github.com/foo/bar/tree/main",
            GitHubLinkType.branch,
            "foo",
            "bar",
            "main",
        ),
        (
            "https://github.com/foo/bar/tree/feat/nested/branch",
            GitHubLinkType.branch,
            "foo",
            "bar",
            "feat/nested/branch",
        ),
        (
            "https://github.com/foo/bar/tree/main/",
            GitHubLinkType.branch,
            "foo",
            "bar",
            "main",
        ),
        (
            "https://github.com/foo/bar/pull/42",
            GitHubLinkType.pull_request,
            "foo",
            "bar",
            "42",
        ),
        (
            "https://github.com/foo/bar/pull/42/files",
            GitHubLinkType.other,
            "foo",
            "bar",
            None,
        ),
        (
            "https://github.com/foo/bar/issues/7",
            GitHubLinkType.issue,
            "foo",
            "bar",
            "7",
        ),
        (
            "https://github.com/foo/bar/actions/runs/12345",
            GitHubLinkType.workflow_run,
            "foo",
            "bar",
            "12345",
        ),
        (
            "https://github.com/foo/bar/wiki",
            GitHubLinkType.other,
            "foo",
            "bar",
            None,
        ),
        (
            "https://github.com/foo/bar/pull/42?diff=split#L10",
            GitHubLinkType.pull_request,
            "foo",
            "bar",
            "42",
        ),
    ],
)
def test_parse_github_url_happy_path(url, expected_type, owner, repo, ref):
    parsed = parse_github_url(url)
    assert parsed is not None
    assert parsed.link_type is expected_type
    assert parsed.owner == owner
    assert parsed.repo == repo
    assert parsed.ref == ref


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "ftp://github.com/foo/bar",
        "https://gitlab.com/foo/bar",
        "https://example.com/foo/bar",
        "https://github.com/",
        "https://github.com/onlyowner",
    ],
)
def test_parse_github_url_invalid(url):
    assert parse_github_url(url) is None


def test_parse_github_url_strips_whitespace():
    parsed = parse_github_url("  https://github.com/foo/bar/pull/1  ")
    assert parsed is not None
    assert parsed.link_type is GitHubLinkType.pull_request
    assert parsed.ref == "1"
