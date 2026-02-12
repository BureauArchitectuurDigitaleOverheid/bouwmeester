"""ArchiMate Model Exchange File Format export service.

Generates XML conforming to The Open Group ArchiMate Exchange Format,
importable by Archi (open source) and BiZZdesign (commercial).
"""

import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge

# Bouwmeester node_type → ArchiMate element type
NODE_TYPE_TO_ARCHIMATE: dict[str, str] = {
    "dossier": "Grouping",
    "doel": "Goal",
    "instrument": "Capability",
    "beleidskader": "Principle",
    "maatregel": "CourseOfAction",
    "politieke_input": "Driver",
    "probleem": "Driver",
    "effect": "Outcome",
    "beleidsoptie": "CourseOfAction",
    "bron": "Resource",
}

# Bouwmeester edge type → ArchiMate relationship type
EDGE_TYPE_TO_ARCHIMATE: dict[str, str] = {
    "draagt_bij_aan": "Influence",
    "implementeert": "Realization",
    "vloeit_voort_uit": "Association",
    "conflicteert_met": "Association",
    "verwijst_naar": "Association",
    "vereist": "Serving",
    "evalueert": "Association",
    "vervangt": "Association",
    "onderdeel_van": "Composition",
    "leidt_tot": "Triggering",
    "adresseert": "Influence",
    "meet": "Association",
    "aanvulling_op": "Aggregation",
}

ARCHIMATE_NS = "http://www.opengroup.org/xsd/archimate/3.0/"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


class ArchiMateExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def export_archimate_xml(self) -> str:
        """Export full corpus as ArchiMate Exchange Format XML."""
        nodes_stmt = select(CorpusNode).order_by(CorpusNode.created_at.desc())
        nodes_result = await self.session.execute(nodes_stmt)
        nodes = list(nodes_result.scalars().all())

        edges_stmt = select(Edge).order_by(Edge.created_at.desc())
        edges_result = await self.session.execute(edges_stmt)
        edges = list(edges_result.scalars().all())

        return self._build_xml(nodes, edges)

    def _build_xml(
        self,
        nodes: list[CorpusNode],
        edges: list[Edge],
    ) -> str:
        root = ET.Element("model")
        root.set("xmlns", ARCHIMATE_NS)
        root.set("xmlns:xsi", XSI_NS)
        root.set(
            "xsi:schemaLocation",
            f"{ARCHIMATE_NS} archimate3_Model.xsd",
        )
        model_id = str(uuid.uuid4())
        root.set("identifier", f"id-{model_id}")

        # Name and metadata
        name_el = ET.SubElement(root, "name")
        name_el.set("xml:lang", "nl")
        name_el.text = "Bouwmeester Corpus"

        metadata = ET.SubElement(root, "metadata")
        schema = ET.SubElement(metadata, "schema")
        schema.text = "http://www.opengroup.org/xsd/archimate/3.0/"
        schema_ver = ET.SubElement(metadata, "schemaversion")
        schema_ver.text = "3.1"

        # Elements
        elements_el = ET.SubElement(root, "elements")
        for node in nodes:
            archimate_type = NODE_TYPE_TO_ARCHIMATE.get(node.node_type, "Grouping")
            elem = ET.SubElement(elements_el, "element")
            elem.set("identifier", f"id-{node.id}")
            elem.set("xsi:type", archimate_type)

            elem_name = ET.SubElement(elem, "name")
            elem_name.set("xml:lang", "nl")
            elem_name.text = node.title

            if node.description:
                doc = ET.SubElement(elem, "documentation")
                doc.set("xml:lang", "nl")
                doc.text = node.description

            # Add properties for Bouwmeester metadata
            props = ET.SubElement(elem, "properties")

            prop_type = ET.SubElement(props, "property")
            prop_type.set("propertyDefinitionRef", "pd-node-type")
            val = ET.SubElement(prop_type, "value")
            val.set("xml:lang", "nl")
            val.text = node.node_type

            if node.status:
                prop_status = ET.SubElement(props, "property")
                prop_status.set("propertyDefinitionRef", "pd-status")
                val_s = ET.SubElement(prop_status, "value")
                val_s.set("xml:lang", "nl")
                val_s.text = node.status

        # Relationships
        rels_el = ET.SubElement(root, "relationships")
        for edge in edges:
            archimate_rel = EDGE_TYPE_TO_ARCHIMATE.get(edge.edge_type_id, "Association")
            rel = ET.SubElement(rels_el, "relationship")
            rel.set("identifier", f"id-{edge.id}")
            rel.set("xsi:type", archimate_rel)
            rel.set("source", f"id-{edge.from_node_id}")
            rel.set("target", f"id-{edge.to_node_id}")

            if edge.description:
                doc = ET.SubElement(rel, "documentation")
                doc.set("xml:lang", "nl")
                doc.text = edge.description

            # Store original edge type as property
            props = ET.SubElement(rel, "properties")
            prop_et = ET.SubElement(props, "property")
            prop_et.set("propertyDefinitionRef", "pd-edge-type")
            val_et = ET.SubElement(prop_et, "value")
            val_et.set("xml:lang", "nl")
            val_et.text = edge.edge_type_id

        # Property definitions
        prop_defs = ET.SubElement(root, "propertyDefinitions")

        pd_nt = ET.SubElement(prop_defs, "propertyDefinition")
        pd_nt.set("identifier", "pd-node-type")
        pd_nt.set("type", "string")
        pd_nt_name = ET.SubElement(pd_nt, "name")
        pd_nt_name.set("xml:lang", "nl")
        pd_nt_name.text = "Bouwmeester Node Type"

        pd_st = ET.SubElement(prop_defs, "propertyDefinition")
        pd_st.set("identifier", "pd-status")
        pd_st.set("type", "string")
        pd_st_name = ET.SubElement(pd_st, "name")
        pd_st_name.set("xml:lang", "nl")
        pd_st_name.text = "Status"

        pd_et = ET.SubElement(prop_defs, "propertyDefinition")
        pd_et.set("identifier", "pd-edge-type")
        pd_et.set("type", "string")
        pd_et_name = ET.SubElement(pd_et, "name")
        pd_et_name.set("xml:lang", "nl")
        pd_et_name.text = "Bouwmeester Edge Type"

        # Organization (group by node_type)
        org_el = ET.SubElement(root, "organizations")
        type_groups: dict[str, list[str]] = {}
        for node in nodes:
            type_groups.setdefault(node.node_type, []).append(str(node.id))
        for node_type, node_ids in type_groups.items():
            item = ET.SubElement(org_el, "item")
            label = ET.SubElement(item, "label")
            label.set("xml:lang", "nl")
            label.text = node_type.replace("_", " ").title()
            for nid in node_ids:
                sub = ET.SubElement(item, "item")
                sub.set("identifierRef", f"id-{nid}")

        # Generate XML string
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        xml_str = ET.tostring(root, encoding="unicode", xml_declaration=False)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f"<!-- Exported from Bouwmeester on {now} -->\n" + xml_str
        )
