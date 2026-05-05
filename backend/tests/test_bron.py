"""Tests for Bron node type and bijlage (file attachment) endpoints."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.bron import Bron
from bouwmeester.models.bron_bijlage import BronBijlage
from bouwmeester.models.chat_attachment import ChatAttachment
from bouwmeester.models.corpus_node import CorpusNode


@pytest.fixture
async def bron_node(db_session: AsyncSession):
    """Create a bron corpus node with its extension row."""
    node_id = uuid.uuid4()
    node = CorpusNode(
        id=node_id,
        title="Test bron",
        node_type="bron",
        description="Een testbron",
        status="actief",
    )
    db_session.add(node)
    await db_session.flush()

    bron = Bron(
        id=node_id,
        type="rapport",
        auteur="Jan Janssen",
        url="https://example.com/rapport.pdf",
    )
    db_session.add(bron)
    await db_session.flush()
    return node


# ---------------------------------------------------------------------------
# Create bron node via API
# ---------------------------------------------------------------------------


async def test_create_bron_node(client):
    """POST /api/nodes with node_type=bron creates node + bron extension."""
    payload = {
        "title": "Nieuw bronrapport",
        "description": "Rapport omschrijving",
        "node_type": "bron",
        "status": "actief",
    }
    resp = await client.post("/api/nodes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["node_type"] == "bron"
    assert data["title"] == "Nieuw bronrapport"

    # Bron extension should exist (default type = overig)
    detail_resp = await client.get(f"/api/nodes/{data['id']}/bron-detail")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["type"] == "overig"


# ---------------------------------------------------------------------------
# Bron detail GET / PUT
# ---------------------------------------------------------------------------


async def test_get_bron_detail(client, bron_node):
    """GET /api/nodes/{id}/bron-detail returns bron-specific fields."""
    resp = await client.get(f"/api/nodes/{bron_node.id}/bron-detail")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "rapport"
    assert data["auteur"] == "Jan Janssen"
    assert data["url"] == "https://example.com/rapport.pdf"


async def test_get_bron_detail_not_found(client, sample_node):
    """GET /api/nodes/{id}/bron-detail returns null for non-bron node."""
    resp = await client.get(f"/api/nodes/{sample_node.id}/bron-detail")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_bron_detail_nonexistent(client):
    """GET /api/nodes/{id}/bron-detail returns 404 for nonexistent node.

    The org-scope check resolves the parent node first; missing nodes
    surface as 404 rather than null (consistent with other node detail
    routes since the authz hardening in #270).
    """
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/nodes/{fake_id}/bron-detail")
    assert resp.status_code == 404


async def test_update_bron_detail(client, bron_node):
    """PUT /api/nodes/{id}/bron-detail updates bron fields."""
    resp = await client.put(
        f"/api/nodes/{bron_node.id}/bron-detail",
        json={"type": "advies", "auteur": "Piet Pietersen"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "advies"
    assert data["auteur"] == "Piet Pietersen"
    # url should be unchanged
    assert data["url"] == "https://example.com/rapport.pdf"


async def test_update_bron_detail_clear_optional_field(client, bron_node):
    """PUT can clear nullable fields by sending null."""
    resp = await client.put(
        f"/api/nodes/{bron_node.id}/bron-detail",
        json={"auteur": None},
    )
    assert resp.status_code == 200
    assert resp.json()["auteur"] is None


async def test_update_bron_detail_not_found(client):
    """PUT /api/nodes/{id}/bron-detail returns 404 for nonexistent bron."""
    fake_id = uuid.uuid4()
    resp = await client.put(
        f"/api/nodes/{fake_id}/bron-detail",
        json={"type": "rapport"},
    )
    assert resp.status_code == 404


async def test_update_bron_detail_invalid_type(client, bron_node):
    """PUT rejects invalid bron type."""
    resp = await client.put(
        f"/api/nodes/{bron_node.id}/bron-detail",
        json={"type": "niet_bestaand"},
    )
    assert resp.status_code == 422


async def test_update_bron_detail_invalid_url(client, bron_node):
    """PUT rejects URL without http(s) scheme."""
    resp = await client.put(
        f"/api/nodes/{bron_node.id}/bron-detail",
        json={"url": "javascript:alert(1)"},
    )
    assert resp.status_code == 422


async def test_update_bron_detail_valid_url(client, bron_node):
    """PUT accepts valid http(s) URL."""
    resp = await client.put(
        f"/api/nodes/{bron_node.id}/bron-detail",
        json={"url": "https://wetten.overheid.nl/BWBR0001840"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"] == "https://wetten.overheid.nl/BWBR0001840"


# ---------------------------------------------------------------------------
# Bijlage upload / info / download / delete
# ---------------------------------------------------------------------------


@pytest.fixture
def bijlagen_tmp(tmp_path: Path):
    """Patch BIJLAGEN_ROOT to a temp directory for file-related tests."""
    with (
        patch("bouwmeester.api.routes.bijlage.BIJLAGEN_ROOT", tmp_path),
        patch("bouwmeester.core.storage.bijlagen_root", return_value=tmp_path),
    ):
        yield tmp_path


async def test_upload_bijlage(client, bron_node, bijlagen_tmp):
    """POST /api/nodes/{id}/bijlage uploads a file."""
    resp = await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["bestandsnaam"] == "test.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["bestandsgrootte"] == len(b"%PDF-1.4 fake content")
    assert "id" in data
    assert "created_at" in data

    # Verify file exists on disk
    node_dir = bijlagen_tmp / str(bron_node.id)
    assert node_dir.exists()
    files = list(node_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith("_test.pdf")


async def test_upload_bijlage_replaces_existing(client, bron_node, bijlagen_tmp):
    """Uploading a second file replaces the first."""
    await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("first.pdf", b"first content", "application/pdf")},
    )
    resp = await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("second.pdf", b"second content", "application/pdf")},
    )
    assert resp.status_code == 201
    assert resp.json()["bestandsnaam"] == "second.pdf"

    # Only one file should remain on disk
    node_dir = bijlagen_tmp / str(bron_node.id)
    files = list(node_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith("_second.pdf")


async def test_upload_bijlage_invalid_content_type(client, bron_node, bijlagen_tmp):
    """Upload rejects disallowed content types."""
    resp = await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("hack.html", b"<script>alert(1)</script>", "text/html")},
    )
    assert resp.status_code == 400
    assert "Ongeldig bestandstype" in resp.json()["detail"]


async def test_upload_bijlage_non_bron_node(client, sample_node, bijlagen_tmp):
    """Upload returns 404 for non-bron nodes."""
    resp = await client.post(
        f"/api/nodes/{sample_node.id}/bijlage",
        files={"file": ("test.pdf", b"content", "application/pdf")},
    )
    assert resp.status_code == 404


async def test_get_bijlage_info(client, bron_node, bijlagen_tmp):
    """GET /api/nodes/{id}/bijlage returns metadata after upload."""
    await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
    )
    resp = await client.get(f"/api/nodes/{bron_node.id}/bijlage")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bestandsnaam"] == "doc.pdf"


async def test_get_bijlage_info_none(client, bron_node):
    """GET /api/nodes/{id}/bijlage returns null when no attachment."""
    resp = await client.get(f"/api/nodes/{bron_node.id}/bijlage")
    assert resp.status_code == 200
    assert resp.json() is None


async def test_download_bijlage(client, bron_node, bijlagen_tmp):
    """GET /api/nodes/{id}/bijlage/download returns the file."""
    file_content = b"%PDF-1.4 test download content"
    await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("download.pdf", file_content, "application/pdf")},
    )
    resp = await client.get(f"/api/nodes/{bron_node.id}/bijlage/download")
    assert resp.status_code == 200
    assert resp.content == file_content
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert resp.headers.get("content-type") == "application/pdf"


async def test_download_bijlage_not_found(client, bron_node):
    """GET /api/nodes/{id}/bijlage/download returns 404 when no attachment."""
    resp = await client.get(f"/api/nodes/{bron_node.id}/bijlage/download")
    assert resp.status_code == 404


async def test_delete_bijlage(client, bron_node, bijlagen_tmp):
    """DELETE /api/nodes/{id}/bijlage removes file and DB record."""
    await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("delete_me.pdf", b"to delete", "application/pdf")},
    )
    resp = await client.delete(f"/api/nodes/{bron_node.id}/bijlage")
    assert resp.status_code == 204

    # File should be gone
    node_dir = bijlagen_tmp / str(bron_node.id)
    assert list(node_dir.iterdir()) == []

    # Info should return null
    info_resp = await client.get(f"/api/nodes/{bron_node.id}/bijlage")
    assert info_resp.status_code == 200
    assert info_resp.json() is None


async def test_delete_bijlage_not_found(client, bron_node):
    """DELETE /api/nodes/{id}/bijlage returns 404 when no attachment."""
    resp = await client.delete(f"/api/nodes/{bron_node.id}/bijlage")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Node delete cascades to bijlage files
# ---------------------------------------------------------------------------


async def test_delete_bron_node_cleans_up_files(client, bron_node, bijlagen_tmp):
    """Deleting a bron node also removes bijlage files from disk."""
    await client.post(
        f"/api/nodes/{bron_node.id}/bijlage",
        files={"file": ("cascade.pdf", b"cascade content", "application/pdf")},
    )
    # Verify file exists
    node_dir = bijlagen_tmp / str(bron_node.id)
    assert len(list(node_dir.iterdir())) == 1

    # Delete the node — bijlagen_tmp fixture already patches BIJLAGEN_ROOT
    # in the bijlage module, and the delete handler imports from there.
    resp = await client.delete(f"/api/nodes/{bron_node.id}")
    assert resp.status_code == 204

    # File should be gone
    assert list(node_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# attach_to_bron chat tool
# ---------------------------------------------------------------------------


@pytest.fixture
async def chat_attachment(db_session: AsyncSession, bijlagen_tmp):
    """Create a chat attachment with a file on disk."""
    att_id = uuid.uuid4()
    filename = "test_doc.pdf"
    safe_name = f"{att_id.hex}_{filename}"
    relative_path = f"{att_id}/{safe_name}"

    # Write the file to the chat subdirectory
    chat_dir = bijlagen_tmp / "chat" / str(att_id)
    chat_dir.mkdir(parents=True)
    file_path = chat_dir / safe_name
    file_path.write_bytes(b"%PDF-1.4 fake chat attachment")

    att = ChatAttachment(
        id=att_id,
        bestandsnaam=filename,
        content_type="application/pdf",
        bestandsgrootte=29,
        pad=relative_path,
    )
    db_session.add(att)
    await db_session.flush()
    return att


async def test_attach_to_bron_happy_path(
    db_session: AsyncSession, bron_node, chat_attachment, bijlagen_tmp
):
    """attach_to_bron copies the file and creates a BronBijlage record."""
    from bouwmeester.services.chat_service import _execute_write_tool

    result = await _execute_write_tool(
        "attach_to_bron",
        {
            "attachment_id": str(chat_attachment.id),
            "node_id": str(bron_node.id),
        },
        db_session,
    )
    assert result["success"] is True
    assert "gekoppeld" in result["summary"]
    assert result["entity_id"] == str(bron_node.id)
    assert result["entity_type"] == "node"

    # BronBijlage record should exist
    stmt = select(BronBijlage).where(BronBijlage.bron_id == bron_node.id)
    row = (await db_session.execute(stmt)).scalar_one()
    assert row.bestandsnaam == "test_doc.pdf"
    assert row.content_type == "application/pdf"

    # File should exist in the bron directory
    bron_dir = bijlagen_tmp / str(bron_node.id)
    files = list(bron_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith("_test_doc.pdf")

    # Original chat file should still exist (copy, not move)
    chat_file = bijlagen_tmp / "chat" / chat_attachment.pad
    assert chat_file.exists()


async def test_attach_to_bron_attachment_not_found(
    db_session: AsyncSession, bron_node, bijlagen_tmp
):
    """attach_to_bron fails gracefully when attachment doesn't exist."""
    from bouwmeester.services.chat_service import _execute_write_tool

    result = await _execute_write_tool(
        "attach_to_bron",
        {
            "attachment_id": str(uuid.uuid4()),
            "node_id": str(bron_node.id),
        },
        db_session,
    )
    assert result["success"] is False
    assert "niet gevonden" in result["summary"]


async def test_attach_to_bron_non_bron_node(
    db_session: AsyncSession, sample_node, chat_attachment, bijlagen_tmp
):
    """attach_to_bron fails when node is not a bron type."""
    from bouwmeester.services.chat_service import _execute_write_tool

    result = await _execute_write_tool(
        "attach_to_bron",
        {
            "attachment_id": str(chat_attachment.id),
            "node_id": str(sample_node.id),
        },
        db_session,
    )
    assert result["success"] is False
    assert "Bron-node niet gevonden" in result["summary"]


async def test_attach_to_bron_existing_bijlage(
    db_session: AsyncSession, bron_node, chat_attachment, bijlagen_tmp
):
    """attach_to_bron rejects when bron already has a bijlage."""
    # Create an existing bijlage
    existing = BronBijlage(
        bron_id=bron_node.id,
        bestandsnaam="existing.pdf",
        content_type="application/pdf",
        bestandsgrootte=100,
        pad=f"{bron_node.id}/existing.pdf",
    )
    db_session.add(existing)
    await db_session.flush()

    from bouwmeester.services.chat_service import _execute_write_tool

    result = await _execute_write_tool(
        "attach_to_bron",
        {
            "attachment_id": str(chat_attachment.id),
            "node_id": str(bron_node.id),
        },
        db_session,
    )
    assert result["success"] is False
    assert "al een bijlage" in result["summary"]


async def test_attach_to_bron_disallowed_content_type(
    db_session: AsyncSession, bron_node, bijlagen_tmp
):
    """attach_to_bron rejects content types not in the bron allowlist."""
    # Create a chat attachment with image/gif (allowed in chat, not in bron)
    att_id = uuid.uuid4()
    safe_name = f"{att_id.hex}_animation.gif"
    relative_path = f"{att_id}/{safe_name}"

    chat_dir = bijlagen_tmp / "chat" / str(att_id)
    chat_dir.mkdir(parents=True)
    (chat_dir / safe_name).write_bytes(b"GIF89a fake gif")

    att = ChatAttachment(
        id=att_id,
        bestandsnaam="animation.gif",
        content_type="image/gif",
        bestandsgrootte=15,
        pad=relative_path,
    )
    db_session.add(att)
    await db_session.flush()

    from bouwmeester.services.chat_service import _execute_write_tool

    result = await _execute_write_tool(
        "attach_to_bron",
        {
            "attachment_id": str(att.id),
            "node_id": str(bron_node.id),
        },
        db_session,
    )
    assert result["success"] is False
    assert "niet toegestaan" in result["summary"]
