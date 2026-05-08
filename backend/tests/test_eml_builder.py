"""Unit tests for the .eml builder used by lead-updates."""

from email import message_from_bytes

from bouwmeester.services.eml_builder import build_outlook_draft_eml


def test_x_unsent_header_present():
    eml = build_outlook_draft_eml(subject="hi", to=["a@b.nl"], body_html="<p>hi</p>")
    msg = message_from_bytes(eml)
    assert msg["X-Unsent"] == "1"


def test_to_cc_subject_and_html_alternative():
    eml = build_outlook_draft_eml(
        subject="Onderwerp",
        to=["a@b.nl", "c@d.nl"],
        cc=["e@f.nl"],
        body_html="<p>Hallo</p>",
    )
    msg = message_from_bytes(eml)
    assert msg["Subject"] == "Onderwerp"
    assert "a@b.nl" in msg["To"]
    assert "c@d.nl" in msg["To"]
    assert msg["Cc"] == "e@f.nl"
    assert msg.is_multipart()
    payload_types = [p.get_content_type() for p in msg.walk()]
    assert "text/plain" in payload_types
    assert "text/html" in payload_types


def test_empty_to_and_cc_omitted():
    eml = build_outlook_draft_eml(subject="hi", to=[], cc=None, body_html="<p>x</p>")
    msg = message_from_bytes(eml)
    assert msg["To"] is None
    assert msg["Cc"] is None
