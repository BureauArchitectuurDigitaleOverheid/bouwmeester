"""XML parsing of external sources is hardened with defusedxml (#322).

`_parse_metadata_xml` (FCC OData $metadata) and `_parse_rio` (RIO XML)
both parse XML fetched over HTTP from external systems. With the stdlib
ElementTree an entity-expansion payload expands in-process; defusedxml
must refuse it instead.

Both payloads below are *differential*: verified that stdlib
``xml.etree.ElementTree.fromstring`` expands them, while defusedxml
raises ``EntitiesForbidden``. A `SYSTEM`-entity ("classic XXE") payload
is deliberately not used here: stdlib already rejects it with a
ParseError, so it would pass with or without the hardening and prove
nothing.

Both functions are pure ``(xml_text) -> ...`` so they're testable
without any HTTP mock.
"""

import pytest
from defusedxml.common import EntitiesForbidden, ExternalReferenceForbidden

from bouwmeester.services.fcc_odata_client import _EDM_NS, _EDMX_NS, FccODataClient
from bouwmeester.services.rio_sync import _parse_rio

# Classic billion-laughs: exponential entity expansion.
BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<root>&lol3;</root>"""

# Nested internal entities: stdlib resolves &y; -> &x; expansion; this is
# the surface defusedxml closes by forbidding entity declarations
# outright. (The earlier SYSTEM-entity payload was vacuous: stdlib
# rejects it on its own, so it never demonstrated defusedxml's value.)
NESTED_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE r [
  <!ENTITY x "xxxxxxxxxx">
  <!ENTITY y "&x;&x;&x;&x;&x;">
]>
<r>&y;</r>"""

ENTITY_ATTACKS = [BILLION_LAUGHS, NESTED_ENTITY]


@pytest.mark.parametrize("payload", ENTITY_ATTACKS)
def test_fcc_metadata_parser_rejects_entity_attacks(payload: str) -> None:
    with pytest.raises((EntitiesForbidden, ExternalReferenceForbidden)):
        FccODataClient._parse_metadata_xml(payload)


@pytest.mark.parametrize("payload", ENTITY_ATTACKS)
def test_rio_parser_rejects_entity_attacks(payload: str) -> None:
    with pytest.raises((EntitiesForbidden, ExternalReferenceForbidden)):
        _parse_rio(payload)


def test_fcc_metadata_parser_still_extracts_entity_sets() -> None:
    """A populated $metadata document still parses correctly.

    Asserts on the extracted structure (not just "is a dict") so a real
    parsing regression, e.g. a parser swap that mangles namespaces,
    would fail this test instead of passing vacuously.
    """
    metadata = (
        f'<edmx:Edmx xmlns:edmx="{_EDMX_NS}" Version="4.0">'
        f'<edmx:DataServices><Schema xmlns="{_EDM_NS}" Namespace="FCC">'
        '<EntityType Name="Project">'
        '<Property Name="Id" Type="Edm.Guid"/>'
        '<Property Name="Name" Type="Edm.String"/>'
        '<Property Name="Budget" Type="Edm.Decimal"/>'
        "</EntityType>"
        '<EntityContainer Name="Container">'
        '<EntitySet Name="Projects" EntityType="FCC.Project"/>'
        "</EntityContainer>"
        "</Schema></edmx:DataServices></edmx:Edmx>"
    )

    result = FccODataClient._parse_metadata_xml(metadata)

    assert result["entity_sets"] == {"Projects": ["Id", "Name", "Budget"]}
