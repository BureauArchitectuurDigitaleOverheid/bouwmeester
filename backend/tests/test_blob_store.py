"""The bijlagen store: S3 in production, a directory locally, and the move between.

S3 runs against moto, which implements the same API the MinIO bucket on ZAD
speaks, so the missing-object and size paths are the real botocore ones.
"""

import uuid
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from bouwmeester.core.blob_store import (
    FallbackBlobStore,
    InvalidKeyError,
    LocalBlobStore,
    S3BlobStore,
    normalize_key,
    set_blob_store,
)
from bouwmeester.models.chat_attachment import ChatAttachment
from bouwmeester.services.bijlagen_migration import (
    check_database_against_store,
    copy_directory_to_store,
)

BUCKET = "bouwmeester-test"


@pytest.fixture
def s3_store():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3BlobStore(client, BUCKET)


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    ["", "/etc/passwd", "../x", "a/../../x", "..", ".", "a\\b", "a\x00b"],
)
def test_normalize_key_rejects_keys_that_leave_the_store(key):
    with pytest.raises(InvalidKeyError):
        normalize_key(key)


def test_normalize_key_keeps_a_normal_path():
    assert normalize_key("leads/abc/123_x.pdf") == "leads/abc/123_x.pdf"
    assert normalize_key("chat//a/./b.png") == "chat/a/b.png"


# ---------------------------------------------------------------------------
# Both stores behave the same
# ---------------------------------------------------------------------------


@pytest.fixture(params=["local", "s3"])
def store(request, tmp_path):
    if request.param == "local":
        yield LocalBlobStore(tmp_path)
    else:
        yield request.getfixturevalue("s3_store")


async def test_put_get_size_delete(store):
    await store.put("chat/a/1_x.txt", b"hallo", "text/plain")

    assert await store.get("chat/a/1_x.txt") == b"hallo"
    assert await store.size("chat/a/1_x.txt") == 5

    await store.delete("chat/a/1_x.txt")
    assert await store.get("chat/a/1_x.txt") is None
    assert await store.size("chat/a/1_x.txt") is None


async def test_missing_object_is_none_not_an_error(store):
    assert await store.get("bestaat/niet.pdf") is None
    assert await store.size("bestaat/niet.pdf") is None
    await store.delete("bestaat/niet.pdf")


async def test_invalid_key_is_refused(store):
    with pytest.raises(InvalidKeyError):
        await store.get("../../etc/passwd")
    with pytest.raises(InvalidKeyError):
        await store.put("/abs", b"x")


# ---------------------------------------------------------------------------
# The move from the volume
# ---------------------------------------------------------------------------


async def test_fallback_serves_a_file_only_the_volume_has(s3_store, tmp_path):
    volume = LocalBlobStore(tmp_path)
    await volume.put("leads/l/1_oud.pdf", b"oud")
    store = FallbackBlobStore(s3_store, volume)

    assert await store.get("leads/l/1_oud.pdf") == b"oud"
    assert await store.size("leads/l/1_oud.pdf") == 3

    # New files go to the bucket only.
    await store.put("leads/l/2_nieuw.pdf", b"nieuw")
    assert await s3_store.get("leads/l/2_nieuw.pdf") == b"nieuw"
    assert await volume.get("leads/l/2_nieuw.pdf") is None


async def test_copy_directory_copies_once_and_skips_the_write_check(
    s3_store, tmp_path: Path
):
    (tmp_path / "chat" / "a").mkdir(parents=True)
    (tmp_path / "chat" / "a" / "1_x.png").write_bytes(b"png")
    (tmp_path / "node" / "2_y.pdf").parent.mkdir()
    (tmp_path / "node" / "2_y.pdf").write_bytes(b"pdf!")
    (tmp_path / "chat" / ".write_test_42").write_bytes(b"")

    first = await copy_directory_to_store(tmp_path, s3_store)
    assert (first.copied, first.already_present, first.failed) == (2, 0, [])
    assert await s3_store.get("chat/a/1_x.png") == b"png"
    assert await s3_store.get("node/2_y.pdf") == b"pdf!"
    assert await s3_store.size("chat/.write_test_42") is None

    # Running it again on every start costs a listing, not a second upload.
    second = await copy_directory_to_store(tmp_path, s3_store)
    assert (second.copied, second.already_present) == (0, 2)


async def test_copy_directory_without_a_volume_does_nothing(s3_store, tmp_path):
    report = await copy_directory_to_store(tmp_path / "bestaat-niet", s3_store)
    assert (report.copied, report.already_present, report.failed) == (0, 0, [])


async def test_check_tells_copied_from_volume_only_from_lost(
    db_session, s3_store, tmp_path
):
    volume = LocalBlobStore(tmp_path)
    in_bucket, on_volume, lost = (f"{uuid.uuid4()}/1_{n}.png" for n in "abc")
    await s3_store.put(f"chat/{in_bucket}", b"1")
    await volume.put(f"chat/{on_volume}", b"2")
    for pad in (in_bucket, on_volume, lost):
        db_session.add(
            ChatAttachment(
                bestandsnaam="x.png",
                content_type="image/png",
                bestandsgrootte=1,
                pad=pad,
            )
        )
    await db_session.flush()

    checks = {
        c.table: c
        for c in await check_database_against_store(db_session, s3_store, volume)
    }
    chat = checks["chat_attachment"]
    assert chat.total >= 3
    assert f"chat/{lost}" in chat.missing
    assert f"chat/{in_bucket}" not in chat.missing
    assert f"chat/{on_volume}" not in chat.missing
    assert chat.only_on_volume >= 1


# ---------------------------------------------------------------------------
# The routes, on a bucket
# ---------------------------------------------------------------------------


async def test_chat_upload_and_preview_through_the_bucket(client, s3_store):
    set_blob_store(s3_store)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16

    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("schermafdruk.png", png, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    attachment_id = resp.json()["id"]

    preview = await client.get(f"/api/chat/attachments/{attachment_id}/preview")
    assert preview.status_code == 200
    assert preview.content == png
    assert preview.headers["content-type"] == "image/png"
    assert 'filename="schermafdruk.png"' in preview.headers["content-disposition"]


async def test_download_of_a_missing_file_is_404(client, s3_store, db_session):
    set_blob_store(s3_store)
    attachment = ChatAttachment(
        bestandsnaam="weg.png",
        content_type="image/png",
        bestandsgrootte=1,
        pad=f"{uuid.uuid4()}/1_weg.png",
    )
    db_session.add(attachment)
    await db_session.flush()

    resp = await client.get(f"/api/chat/attachments/{attachment.id}/preview")
    assert resp.status_code == 404
