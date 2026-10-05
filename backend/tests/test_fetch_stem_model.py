"""Tests for the script that puts the speaker model in the image.

Nothing is downloaded here. What is tested is what the build does with
what came back: nothing, the right file, or another one.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import urllib.error

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "fetch_stem_model.py"
_SPEC = importlib.util.spec_from_file_location("fetch_stem_model", _PATH)
fetch_stem_model = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fetch_stem_model)


def test_the_right_file_is_written(tmp_path, monkeypatch):
    data = b"the model"
    monkeypatch.setattr(fetch_stem_model, "SHA256", hashlib.sha256(data).hexdigest())
    target = tmp_path / "opt" / "models" / "model.onnx"

    assert fetch_stem_model.main(target, data) == 0
    assert target.read_bytes() == data


def test_another_file_is_not_kept_and_does_not_fail_the_build(tmp_path, capsys):
    """An error page with status 200 must not block a deploy, and must
    not be taken for the model either."""
    target = tmp_path / "models" / "model.onnx"

    assert fetch_stem_model.main(target, b"something else") == 0
    assert not target.exists()
    assert "verwacht was" in capsys.readouterr().out


def test_no_download_is_an_image_without_the_model(tmp_path):
    """The directory is there, so the image can copy it; the file is not,
    and the application then works by time alone."""
    target = tmp_path / "models" / "model.onnx"

    assert fetch_stem_model.main(target, None) == 0
    assert target.parent.is_dir()
    assert not target.exists()


@pytest.mark.parametrize(
    "error", [urllib.error.URLError("no route"), TimeoutError(), OSError("reset")]
)
def test_a_download_that_fails_is_nothing(monkeypatch, capsys, error):
    def urlopen(url, timeout):
        raise error

    monkeypatch.setattr(fetch_stem_model.urllib.request, "urlopen", urlopen)

    assert fetch_stem_model.fetch() is None
    assert "niet te downloaden" in capsys.readouterr().out


def test_the_download_is_pinned_to_a_revision(monkeypatch):
    asked: list[tuple[str, int]] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"bytes"

    def urlopen(url, timeout):
        asked.append((url, timeout))
        return Response()

    monkeypatch.setattr(fetch_stem_model.urllib.request, "urlopen", urlopen)

    assert fetch_stem_model.fetch() == b"bytes"
    ((url, timeout),) = asked
    assert url.startswith("https://huggingface.co/")
    assert f"/resolve/{fetch_stem_model.REVISION}/" in url
    assert "/main/" not in url
    assert len(fetch_stem_model.REVISION) == 40
    assert len(fetch_stem_model.SHA256) == 64
    assert timeout == fetch_stem_model.TIMEOUT


def test_a_download_that_breaks_off_is_nothing_either(monkeypatch, capsys):
    import http.client

    def broken(url, timeout=None):
        raise http.client.IncompleteRead(b"half")

    monkeypatch.setattr(fetch_stem_model.urllib.request, "urlopen", broken)

    assert fetch_stem_model.fetch() is None
    assert "de image komt zonder" in capsys.readouterr().out
