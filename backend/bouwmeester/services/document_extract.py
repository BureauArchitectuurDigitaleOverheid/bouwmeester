"""Text extraction from uploaded documents (PDF, Word, ODT, TXT)."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Truncate extracted text to stay within LLM token limits.
MAX_EXTRACTED_CHARS = 15_000

# MIME types that are images (handled as vision content, not text extraction).
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def extract_text(path: Path, content_type: str) -> str | None:
    """Extract text from a document file. Returns None for images."""
    if content_type in IMAGE_CONTENT_TYPES:
        return None

    try:
        if content_type == "application/pdf":
            return _extract_pdf(path)
        docx_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        if content_type == docx_type:
            return _extract_docx(path)
        if content_type == "application/msword":
            # Old binary .doc format — python-docx only handles .docx
            logger.info("Skipping text extraction for legacy .doc file: %s", path)
            return None
        if content_type == "application/vnd.oasis.opendocument.text":
            return _extract_odt(path)
        if content_type == "text/plain":
            return _extract_txt(path)
    except Exception:
        logger.exception("Failed to extract text from %s (%s)", path, content_type)
        return None

    return None


def _extract_pdf(path: Path) -> str | None:
    from pdfminer.high_level import extract_text as pdf_extract

    text = pdf_extract(str(path))
    return _truncate(text)


def _extract_docx(path: Path) -> str | None:
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n".join(paragraphs)
    return _truncate(text)


def _extract_odt(path: Path) -> str | None:
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
    return _truncate("\n".join(paragraphs))


def _extract_txt(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8", errors="replace")
    return _truncate(content)


def _truncate(text: str) -> str | None:
    text = text.strip()
    if not text:
        return None
    if len(text) > MAX_EXTRACTED_CHARS:
        return text[:MAX_EXTRACTED_CHARS] + "\n\n[... tekst afgekapt ...]"
    return text
