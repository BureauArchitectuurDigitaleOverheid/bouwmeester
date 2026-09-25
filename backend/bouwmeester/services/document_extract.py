"""Text extraction from uploaded documents (PDF, Word, ODT, TXT)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Truncate extracted text to stay within LLM token limits.
MAX_EXTRACTED_CHARS = 15_000

# MIME types that are images (handled as vision content, not text extraction).
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def extract_text(
    path: Path, content_type: str, max_chars: int = MAX_EXTRACTED_CHARS
) -> str | None:
    """Extract text from a document file. Returns None for images.

    `max_chars` overrides the default cap. Parliamentary documents can run
    to hundreds of thousands of characters and mention a search term
    halfway through, so the caller that searches within the text needs the
    whole thing; it does its own trimming around the match.
    """
    if content_type in IMAGE_CONTENT_TYPES:
        return None

    try:
        if content_type == "application/pdf":
            return _extract_pdf(path, max_chars)
        docx_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        if content_type == docx_type:
            return _extract_docx(path, max_chars)
        if content_type == "application/msword":
            # Old binary .doc format — python-docx only handles .docx
            logger.info("Skipping text extraction for legacy .doc file: %s", path)
            return None
        if content_type == "application/vnd.oasis.opendocument.text":
            return _extract_odt(path, max_chars)
        if content_type == "text/plain":
            return _extract_txt(path, max_chars)
    except Exception:
        logger.exception("Failed to extract text from %s (%s)", path, content_type)
        return None

    return None


def extract_text_from_bytes(
    data: bytes, content_type: str, max_chars: int = MAX_EXTRACTED_CHARS
) -> str | None:
    """`extract_text` for content in memory, such as a file from object storage.

    The extractors read from a path, so the bytes go through a temporary file
    that is removed again afterwards. Blocking: run it in a thread.
    """
    if content_type in IMAGE_CONTENT_TYPES:
        return None

    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return extract_text(tmp_path, content_type, max_chars)
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_pdf(path: Path, max_chars: int = MAX_EXTRACTED_CHARS) -> str | None:
    from pdfminer.high_level import extract_text as pdf_extract

    text = pdf_extract(str(path))
    return _truncate(text, max_chars)


def _extract_docx(path: Path, max_chars: int = MAX_EXTRACTED_CHARS) -> str | None:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return _truncate(text, max_chars)


def _extract_odt(path: Path, max_chars: int = MAX_EXTRACTED_CHARS) -> str | None:
    from odf.opendocument import load
    from odf.text import P

    doc = load(str(path))
    paragraphs = []
    for p in doc.getElementsByType(P):
        text = ""
        for node in p.childNodes:
            if hasattr(node, "data"):
                text += node.data
            elif hasattr(node, "__str__"):
                text += str(node)
        if text.strip():
            paragraphs.append(text)
    return _truncate("\n".join(paragraphs), max_chars)


def _extract_txt(path: Path, max_chars: int = MAX_EXTRACTED_CHARS) -> str | None:
    content = path.read_text(encoding="utf-8", errors="replace")
    return _truncate(content, max_chars)


def _truncate(text: str, max_chars: int = MAX_EXTRACTED_CHARS) -> str | None:
    text = text.strip()
    if not text:
        return None
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[... tekst afgekapt ...]"
    return text
