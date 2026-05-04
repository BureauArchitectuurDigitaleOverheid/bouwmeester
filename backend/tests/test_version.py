"""Tests for the /api/admin/version endpoint constants."""

import importlib
import os


def _reload_admin(env: dict[str, str]):
    for key in ("GIT_SHA", "BUILD_TIME", "REPO_URL"):
        os.environ.pop(key, None)
    for key, value in env.items():
        os.environ[key] = value
    from bouwmeester.api.routes import admin as admin_module

    return importlib.reload(admin_module)


def test_version_info_reads_env_vars():
    """_VERSION_INFO captures the env vars present at module load."""
    try:
        admin = _reload_admin(
            {
                "GIT_SHA": "abc1234",
                "BUILD_TIME": "2026-05-04T10:00:00Z",
                "REPO_URL": "https://github.com/example/repo",
            }
        )
        assert admin._VERSION_INFO == {
            "git_sha": "abc1234",
            "build_time": "2026-05-04T10:00:00Z",
            "repo_url": "https://github.com/example/repo",
        }
    finally:
        _reload_admin({})


def test_version_info_defaults_when_env_absent():
    """Without build args set, sha and build_time are empty; repo_url has a default."""
    admin = _reload_admin({})
    assert admin._VERSION_INFO["git_sha"] == ""
    assert admin._VERSION_INFO["build_time"] == ""
    assert admin._VERSION_INFO["repo_url"].startswith("https://github.com/")
