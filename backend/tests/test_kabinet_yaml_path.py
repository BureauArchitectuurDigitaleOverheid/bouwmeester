"""Tests for the writable kabinet.yaml path resolution.

Regression for the deployed worker crashing with EACCES when it tried to
overwrite kabinet.yaml inside the read-only /app code tree.
"""

from __future__ import annotations

from pathlib import Path

from bouwmeester.core import storage


def test_data_root_uses_data_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    assert storage.data_root() == tmp_path


def test_data_root_defaults_to_data_dir(monkeypatch):
    monkeypatch.delenv("DATA_PATH", raising=False)
    assert storage.data_root() == Path("/data")


def test_kabinet_yaml_path_under_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    target = storage.kabinet_yaml_path()
    assert target == tmp_path / "kabinet.yaml"


def test_kabinet_yaml_path_seeds_from_in_image_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))

    seed = Path(storage.__file__).resolve().parent.parent / "data" / "kabinet.yaml"
    target = storage.kabinet_yaml_path()

    assert target.exists()
    if seed.exists():
        assert target.read_bytes() == seed.read_bytes()


def test_kabinet_yaml_path_does_not_clobber_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_PATH", str(tmp_path))
    existing = tmp_path / "kabinet.yaml"
    existing.write_text("bewindspersonen: []\n")

    target = storage.kabinet_yaml_path()

    assert target.read_text() == "bewindspersonen: []\n"
