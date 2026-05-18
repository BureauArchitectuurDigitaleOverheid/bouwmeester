"""User-uploaded .docx/.odt extraction must not be an XXE vector (#322).

`document_extract.extract_text` is reachable by any authenticated user
via POST /leads/{id}/updates/parse, so a malicious Office file is
attacker-controlled, higher-trust-boundary input than the external-HTTP
XML the rest of #322 hardened.

These parsers are *not* changed in #322 because the libraries already
harden them, which was verified empirically rather than assumed:

- python-docx builds its lxml parser with ``resolve_entities=False``
  (docx/oxml/parser.py), so entity payloads are not expanded.
- odfpy loads via ``defusedxml.sax.make_parser`` (odf/opendocument.py),
  which raises on entity declarations.

This test pins that behaviour so a future dependency downgrade that
reintroduces the hole fails CI instead of shipping silently.
"""

import zipfile
from pathlib import Path

from bouwmeester.services.document_extract import extract_text

DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ODT_CT = "application/vnd.oasis.opendocument.text"

# Entity-expansion payload. If a parser resolves entities, &c; explodes
# into a large string that would surface in the extracted text.
_BILLION = """<?xml version="1.0"?>
<!DOCTYPE doc [
 <!ENTITY a "AAAAAAAAAA">
 <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
 <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
]>"""


def _write_evil_docx(path: Path) -> None:
    document_xml = (
        _BILLION + '<w:document xmlns:w="http://schemas.openxmlformats.org/'
        'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&c;'
        "</w:t></w:r></w:p></w:body></w:document>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.'
            'openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.'
            'openxmlformats.org/package/2006/relationships"><Relationship '
            'Id="rId1" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        z.writestr("word/document.xml", document_xml)


def _write_evil_odt(path: Path) -> None:
    content_xml = (
        _BILLION + '<office:document-content xmlns:office="urn:oasis:names:tc:'
        'opendocument:xmlns:office:1.0" xmlns:text="urn:oasis:names:tc:'
        'opendocument:xmlns:text:1.0"><office:body><office:text>'
        "<text:p>&c;</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr(
            "META-INF/manifest.xml",
            '<?xml version="1.0"?><manifest:manifest xmlns:manifest='
            '"urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
            '<manifest:file-entry manifest:full-path="/" '
            'manifest:media-type="application/vnd.oasis.opendocument.text"/>'
            '<manifest:file-entry manifest:full-path="content.xml" '
            'manifest:media-type="text/xml"/></manifest:manifest>',
        )
        z.writestr("content.xml", content_xml)


def test_docx_upload_does_not_expand_entities(tmp_path: Path) -> None:
    evil = tmp_path / "evil.docx"
    _write_evil_docx(evil)

    text = extract_text(evil, DOCX_CT)

    # python-docx parser has resolve_entities=False: &c; is not expanded,
    # so the bomb never materialises. extract_text returns None for the
    # resulting empty document. The hard assertion is "no expansion".
    assert text is None or "AAAAAAAAAA" not in text


def test_odt_upload_does_not_expand_entities(tmp_path: Path) -> None:
    evil = tmp_path / "evil.odt"
    _write_evil_odt(evil)

    # odfpy uses defusedxml's SAX parser; it raises EntitiesForbidden on
    # the entity declaration. extract_text catches all parse failures and
    # returns None. Either way the bomb must never reach the output.
    text = extract_text(evil, ODT_CT)

    assert text is None or "AAAAAAAAAA" not in text
