"""GitHub URL parsing.

Pikt branch / pull-request / issue / repo / workflow-run URLs op github.com
en levert (link_type, owner, repo, ref). Bewust strikt: alleen github.com
en alleen de vormen die hieronder expliciet matchen tellen, de rest valt
in `other` of is None.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from urllib.parse import urlparse


class GitHubLinkType(enum.StrEnum):
    branch = "branch"
    pull_request = "pull_request"
    issue = "issue"
    repo = "repo"
    workflow_run = "workflow_run"
    other = "other"


@dataclass(frozen=True)
class ParsedGitHubLink:
    link_type: GitHubLinkType
    owner: str
    repo: str
    ref: str | None  # branch-naam, PR/issue-nummer (str), run-id (str)


_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})"
_REPO_RE = r"[A-Za-z0-9._-]+"

_PATTERNS: tuple[tuple[GitHubLinkType, re.Pattern[str]], ...] = (
    (
        GitHubLinkType.pull_request,
        re.compile(
            rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})/pull/(?P<ref>\d+)/?$"
        ),
    ),
    (
        GitHubLinkType.issue,
        re.compile(
            rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})/issues/(?P<ref>\d+)/?$"
        ),
    ),
    (
        GitHubLinkType.workflow_run,
        re.compile(
            rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})/actions/runs/(?P<ref>\d+)/?$"
        ),
    ),
    (
        GitHubLinkType.branch,
        re.compile(
            rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})/tree/(?P<ref>[^?#]+?)/?$"
        ),
    ),
    (
        GitHubLinkType.repo,
        re.compile(rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})/?$"),
    ),
)

_OTHER_RE = re.compile(rf"^/(?P<owner>{_OWNER_RE})/(?P<repo>{_REPO_RE})(?:/.*)?$")


def parse_github_url(url: str) -> ParsedGitHubLink | None:
    """Parse een GitHub-URL of return None als het er geen is.

    Accepteert https://github.com en https://www.github.com. Strikt voor de
    bekende vormen; valt anders terug op `other` zolang het pad in elk
    geval `/owner/repo` is. Trailing slashes worden getolereerd, query- en
    fragment-suffixen worden genegeerd.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    if host not in ("github.com", "www.github.com"):
        return None

    path = parsed.path or "/"

    for link_type, pattern in _PATTERNS:
        match = pattern.match(path)
        if match:
            owner = match.group("owner")
            repo = _strip_git_suffix(match.group("repo"))
            ref = match.groupdict().get("ref")
            if ref is not None:
                ref = ref.rstrip("/")
            return ParsedGitHubLink(
                link_type=link_type, owner=owner, repo=repo, ref=ref
            )

    other = _OTHER_RE.match(path)
    if other:
        return ParsedGitHubLink(
            link_type=GitHubLinkType.other,
            owner=other.group("owner"),
            repo=_strip_git_suffix(other.group("repo")),
            ref=None,
        )

    return None


def _strip_git_suffix(repo: str) -> str:
    if repo.endswith(".git"):
        return repo[: -len(".git")]
    return repo
