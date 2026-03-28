"""Tests for chat attachment upload, preview, and document extraction."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.chat_attachment import ChatAttachment


@pytest.fixture
def chat_bijlagen_tmp(tmp_path: Path):
    """Patch bijlagen roots to a temp directory for chat attachment tests."""
    chat_root = tmp_path / "chat"
    chat_root.mkdir()
    with (
        patch("bouwmeester.api.routes.chat.CHAT_BIJLAGEN_ROOT", chat_root),
        patch("bouwmeester.core.storage.bijlagen_root", return_value=tmp_path),
    ):
        yield tmp_path


# ---------------------------------------------------------------------------
# Upload endpoint tests
# ---------------------------------------------------------------------------


async def test_upload_chat_attachment(client, chat_bijlagen_tmp):
    """POST /api/chat/upload uploads a file and returns metadata."""
    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("test.pdf", b"%PDF-1.4 fake content", "application/pdf")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["bestandsnaam"] == "test.pdf"
    assert data["content_type"] == "application/pdf"
    assert data["bestandsgrootte"] == len(b"%PDF-1.4 fake content")
    assert "id" in data

    # Verify file exists on disk
    chat_root = chat_bijlagen_tmp / "chat"
    att_dir = chat_root / data["id"]
    assert att_dir.exists()
    files = list(att_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith("_test.pdf")


async def test_upload_chat_attachment_image(client, chat_bijlagen_tmp):
    """POST /api/chat/upload accepts image files."""
    # PNG magic bytes
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("photo.png", png_header, "image/png")},
    )
    assert resp.status_code == 201
    assert resp.json()["content_type"] == "image/png"


async def test_upload_rejects_disallowed_content_type(client, chat_bijlagen_tmp):
    """Upload rejects content types not in the allowlist."""
    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("hack.html", b"<script>alert(1)</script>", "text/html")},
    )
    assert resp.status_code == 400
    assert "Ongeldig bestandstype" in resp.json()["detail"]


async def test_upload_rejects_spoofed_content_type(client, chat_bijlagen_tmp):
    """Upload rejects files whose magic bytes don't match claimed content type."""
    # Send a file claiming to be a PDF but with PNG magic bytes
    png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("fake.pdf", png_header, "application/pdf")},
    )
    assert resp.status_code == 400
    assert "komt niet overeen" in resp.json()["detail"]


async def test_upload_rejects_oversized_file(client, chat_bijlagen_tmp):
    """Upload rejects files larger than the size limit."""
    # Patch MAX_UPLOAD_SIZE to a tiny value for testing
    with patch("bouwmeester.core.storage.MAX_UPLOAD_SIZE", 100):
        resp = await client.post(
            "/api/chat/upload",
            files={"file": ("big.pdf", b"%PDF" + b"x" * 200, "application/pdf")},
        )
    assert resp.status_code == 400
    assert "te groot" in resp.json()["detail"]


async def test_upload_sanitizes_filename(client, chat_bijlagen_tmp):
    """Upload strips directory components from filenames."""
    resp = await client.post(
        "/api/chat/upload",
        files={"file": ("../../etc/passwd", b"%PDF-1.4 content", "application/pdf")},
    )
    assert resp.status_code == 201
    data = resp.json()
    # Path traversal components should be stripped
    assert "/" not in data["bestandsnaam"]
    assert ".." not in data["bestandsnaam"]


async def test_upload_error_does_not_leak_path(client, chat_bijlagen_tmp):
    """500 error messages should not contain server filesystem paths."""
    # Make the chat dir read-only to trigger an OSError
    chat_root = chat_bijlagen_tmp / "chat"
    chat_root.chmod(0o444)
    try:
        resp = await client.post(
            "/api/chat/upload",
            files={"file": ("test.pdf", b"%PDF-1.4 content", "application/pdf")},
        )
        assert resp.status_code == 500
        detail = resp.json()["detail"]
        assert "/" not in detail  # No filesystem paths
        assert "Kan bestand niet opslaan" in detail
    finally:
        chat_root.chmod(0o755)


# ---------------------------------------------------------------------------
# Preview endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
async def uploaded_attachment(
    db_session: AsyncSession, chat_bijlagen_tmp, create_person
):
    """Create a chat attachment owned by a specific person."""
    person = await create_person(naam="Uploader", prefix="uploader")
    att_id = uuid.uuid4()
    filename = "preview_test.pdf"
    safe_name = f"{att_id.hex}_{filename}"
    relative_path = f"{att_id}/{safe_name}"

    chat_root = chat_bijlagen_tmp / "chat"
    att_dir = chat_root / str(att_id)
    att_dir.mkdir(parents=True, exist_ok=True)
    (att_dir / safe_name).write_bytes(b"%PDF-1.4 preview content")

    att = ChatAttachment(
        id=att_id,
        person_id=person.id,
        bestandsnaam=filename,
        content_type="application/pdf",
        bestandsgrootte=24,
        pad=relative_path,
    )
    db_session.add(att)
    await db_session.flush()
    return att, person


@pytest.fixture
async def unowned_attachment(db_session: AsyncSession, chat_bijlagen_tmp):
    """Create a chat attachment with no person_id (unowned)."""
    att_id = uuid.uuid4()
    filename = "unowned.pdf"
    safe_name = f"{att_id.hex}_{filename}"
    relative_path = f"{att_id}/{safe_name}"

    chat_root = chat_bijlagen_tmp / "chat"
    att_dir = chat_root / str(att_id)
    att_dir.mkdir(parents=True, exist_ok=True)
    (att_dir / safe_name).write_bytes(b"%PDF-1.4 unowned content")

    att = ChatAttachment(
        id=att_id,
        person_id=None,
        bestandsnaam=filename,
        content_type="application/pdf",
        bestandsgrootte=25,
        pad=relative_path,
    )
    db_session.add(att)
    await db_session.flush()
    return att


async def test_preview_returns_file(client, unowned_attachment, chat_bijlagen_tmp):
    """GET /api/chat/attachments/{id}/preview returns the file."""
    att = unowned_attachment
    resp = await client.get(f"/api/chat/attachments/{att.id}/preview")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 unowned content"


async def test_preview_nonexistent_returns_404(client, chat_bijlagen_tmp):
    """Preview returns 404 for nonexistent attachment IDs."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/chat/attachments/{fake_id}/preview")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document extraction tests
# ---------------------------------------------------------------------------


def test_extract_txt():
    """extract_text handles plain text files."""
    import tempfile

    from bouwmeester.services.document_extract import extract_text

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("Hallo wereld\nDit is een test.")
        f.flush()
        result = extract_text(Path(f.name), "text/plain")
    assert result == "Hallo wereld\nDit is een test."


def test_extract_txt_empty():
    """extract_text returns None for empty text files."""
    import tempfile

    from bouwmeester.services.document_extract import extract_text

    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("")
        f.flush()
        result = extract_text(Path(f.name), "text/plain")
    assert result is None


def test_extract_txt_truncation():
    """extract_text truncates text exceeding the limit."""
    import tempfile

    from bouwmeester.services.document_extract import MAX_EXTRACTED_CHARS, extract_text

    long_text = "x" * (MAX_EXTRACTED_CHARS + 1000)
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write(long_text)
        f.flush()
        result = extract_text(Path(f.name), "text/plain")
    assert result is not None
    assert len(result) < len(long_text)
    assert result.endswith("[... tekst afgekapt ...]")


def test_extract_image_returns_none():
    """extract_text returns None for image content types."""
    from bouwmeester.services.document_extract import extract_text

    result = extract_text(Path("/nonexistent"), "image/png")
    assert result is None


def test_extract_doc_returns_none():
    """extract_text returns None for legacy .doc files."""
    from bouwmeester.services.document_extract import extract_text

    result = extract_text(Path("/nonexistent"), "application/msword")
    assert result is None


def test_extract_unknown_type_returns_none():
    """extract_text returns None for unknown content types."""
    from bouwmeester.services.document_extract import extract_text

    result = extract_text(Path("/nonexistent"), "application/octet-stream")
    assert result is None


# ---------------------------------------------------------------------------
# Content-type verification (magic bytes)
# ---------------------------------------------------------------------------


def test_verify_content_type_pdf_valid():
    """PDF magic bytes match application/pdf."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"%PDF-1.4 content", "application/pdf") is True


def test_verify_content_type_pdf_spoofed():
    """PNG bytes don't match application/pdf."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"\x89PNG\r\n", "application/pdf") is False


def test_verify_content_type_png_valid():
    """PNG magic bytes match image/png."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"\x89PNG\r\n\x1a\n", "image/png") is True


def test_verify_content_type_jpeg_valid():
    """JPEG magic bytes match image/jpeg."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"\xff\xd8\xff\xe0", "image/jpeg") is True


def test_verify_content_type_text_always_passes():
    """text/plain always passes regardless of content."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"\x89PNG binary garbage", "text/plain") is True


def test_verify_content_type_unknown_signature_passes():
    """Files with no recognized magic signature pass validation."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"\x00\x01\x02\x03", "application/pdf") is True


def test_verify_content_type_gif_valid():
    """GIF magic bytes match image/gif."""
    from bouwmeester.core.storage import verify_content_type

    assert verify_content_type(b"GIF89a", "image/gif") is True


def test_verify_content_type_docx_valid():
    """PK (zip) magic bytes match docx."""
    from bouwmeester.core.storage import verify_content_type

    ct = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert verify_content_type(b"PK\x03\x04", ct) is True


def test_verify_content_type_old_doc_valid():
    """OLE2 magic bytes match application/msword."""
    from bouwmeester.core.storage import verify_content_type

    content = b"\xd0\xcf\x11\xe0\xa1\xb1"
    assert verify_content_type(content, "application/msword") is True
