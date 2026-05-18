"""XML parsing of external sources is hardened with defusedxml (#322).

`_parse_metadata_xml` (FCC OData $metadata) and `_parse_rio` (RIO XML)
both parse XML fetched over HTTP from external systems. With the stdlib
ElementTree an entity-expansion ("billion laughs") or external-entity
payload would expand / fetch. defusedxml must refuse both instead.

Both functions are pure ``(xml_text) -> ...`` so they're testable
without any HTTP mock.
"""

import pytest
from defusedxml.common import EntitiesForbidden, ExternalReferenceForbidden

from bouwmeester.services.fcc_odata_client import FccODataClient
from bouwmeester.services.rio_sync import _parse_rio

BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>&lol3;</root>"""

EXTERNAL_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>"""


@pytest.mark.parametrize("payload", [BILLION_LAUGHS, EXTERNAL_ENTITY])
def test_fcc_metadata_parser_rejects_entity_attacks(payload: str) -> None:
    with pytest.raises((EntitiesForbidden, ExternalReferenceForbidden)):
        FccODataClient._parse_metadata_xml(payload)


@pytest.mark.parametrize("payload", [BILLION_LAUGHS, EXTERNAL_ENTITY])
def test_rio_parser_rejects_entity_attacks(payload: str) -> None:
    with pytest.raises((EntitiesForbidden, ExternalReferenceForbidden)):
        _parse_rio(payload)


def test_fcc_metadata_parser_still_parses_clean_xml() -> None:
    """A benign $metadata document still parses (no regression)."""
    clean = (
        '<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" '
        'Version="4.0"><edmx:DataServices/></edmx:Edmx>'
    )
    # Should not raise; empty doc yields an empty mapping.
    result = FccODataClient._parse_metadata_xml(clean)
    assert isinstance(result, dict)
