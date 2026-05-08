"""Build .eml files Outlook (Windows) opens as a new editable draft.

The X-Unsent: 1 header is what flips Outlook from read-mode to compose-mode
when the user double-clicks the saved message. Without it the .eml opens as a
read-only received message and the recipients cannot be edited inline.
"""

from email.message import EmailMessage


def build_outlook_draft_eml(
    *,
    subject: str,
    to: list[str],
    cc: list[str] | None = None,
    body_html: str,
    body_text: str | None = None,
    from_addr: str | None = None,
) -> bytes:
    """Return raw bytes of an RFC 5322 message ready as a .eml download.

    `body_html` is the rich body (already HTML, not Markdown). `body_text` is
    the plain-text fallback; if omitted we strip tags from the HTML so the
    message remains a proper multipart/alternative.
    """
    msg = EmailMessage()
    msg["Subject"] = subject or ""
    if from_addr:
        msg["From"] = from_addr
    if to:
        msg["To"] = ", ".join(addr for addr in to if addr)
    if cc:
        msg["Cc"] = ", ".join(addr for addr in cc if addr)
    msg["X-Unsent"] = "1"

    plain = body_text if body_text is not None else _strip_html(body_html)
    msg.set_content(plain or "")
    msg.add_alternative(body_html or "", subtype="html")

    return bytes(msg)


def _strip_html(html: str) -> str:
    """Cheap HTML→text fallback for the plain-text alternative.

    We don't pull in a parser dependency here: this is a fallback most clients
    won't render anyway (Outlook will pick the HTML alternative).
    """
    import re

    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()
