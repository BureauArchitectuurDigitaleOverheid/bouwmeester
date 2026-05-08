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


def test_markdown_to_html_handles_multiple_bold_segments():
    """Regression: ``**a** **b**`` must produce two <strong>, not one greedy
    span swallowing the space between them."""
    from bouwmeester.services.markdown_min import markdown_to_html

    out = markdown_to_html("**a** **b**")
    assert out == "<p><strong>a</strong> <strong>b</strong></p>"


def test_markdown_to_html_escapes_html_in_input():
    from bouwmeester.services.markdown_min import markdown_to_html

    out = markdown_to_html("<script>alert(1)</script> & co")
    assert "<script>" not in out
    assert "&amp;" in out


def test_markdown_to_html_renders_bullet_list():
    from bouwmeester.services.markdown_min import markdown_to_html

    out = markdown_to_html("- een\n- twee")
    assert out == "<ul><li>een</li><li>twee</li></ul>"
