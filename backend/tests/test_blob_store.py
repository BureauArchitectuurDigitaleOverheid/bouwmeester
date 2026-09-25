"""The bijlagen store: S3 in production, a directory locally.

S3 runs against moto, which implements the same API the MinIO bucket on ZAD
speaks, so the missing-object and size paths are the real botocore ones.
"""

import uuid

import boto3
import pytest
from moto import mock_aws

from bouwmeester.core.blob_store import (
    InvalidKeyError,
    LocalBlobStore,
    S3BlobStore,
    normalize_key,
    set_blob_store,
)
from bouwmeester.models.chat_attachment import ChatAttachment
from bouwmeester.services.bijlagen_check import check_database_against_store

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
# The database against the store
# ---------------------------------------------------------------------------


async def test_check_counts_files_the_store_lacks(db_session, s3_store):
    present, lost = (f"{uuid.uuid4()}/1_{n}.png" for n in "ab")
    await s3_store.put(f"chat/{present}", b"1")
    for pad in (present, lost):
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
        c.table: c for c in await check_database_against_store(db_session, s3_store)
    }
    chat = checks["chat_attachment"]
    assert chat.total >= 2
    assert chat.present >= 1
    assert f"chat/{lost}" in chat.missing
    assert f"chat/{present}" not in chat.missing


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
