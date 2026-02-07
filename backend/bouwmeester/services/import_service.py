"""Service layer for bulk import operations."""

import csv
import io
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.models.corpus_node import CorpusNode
from bouwmeester.models.edge import Edge
from bouwmeester.models.politieke_input import PolitiekeInput
from bouwmeester.schema.import_export import ImportResult


class ImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def import_politieke_inputs_csv(self, file_content: bytes) -> ImportResult:
        """Parse CSV with columns: title, type, referentie, datum, description, status.

        Creates a CorpusNode + PolitiekeInput for each row.
        """
        imported = 0
        skipped = 0
        errors: list[str] = []

        text_content = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text_content))

        valid_types = {
            "coalitieakkoord",
            "motie",
            "kamerbrief",
            "toezegging",
            "amendement",
        }

        for row_num, row in enumerate(reader, start=2):
            try:
                title = row.get("title", "").strip()
                pi_type = row.get("type", "").strip()
                referentie = row.get("referentie", "").strip() or None
                datum_str = row.get("datum", "").strip()
                description = row.get("description", "").strip() or None
                status = row.get("status", "").strip() or "open"

                if not title:
                    errors.append(f"Rij {row_num}: titel ontbreekt")
                    skipped += 1
                    continue

                if pi_type not in valid_types:
                    errors.append(
                        f"Rij {row_num}: ongeldig type '{pi_type}' "
                        f"(verwacht: {', '.join(sorted(valid_types))})"
                    )
                    skipped += 1
                    continue

                datum: date | None = None
                if datum_str:
                    try:
                        datum = datetime.strptime(datum_str, "%Y-%m-%d").date()
                    except ValueError:
                        errors.append(
                            f"Rij {row_num}: ongeldige datum '{datum_str}' "
                            f"(verwacht: YYYY-MM-DD)"
                        )
                        skipped += 1
                        continue

                # Create CorpusNode
                node = CorpusNode(
                    title=title,
                    node_type="politieke_input",
                    description=description,
                    status="actief",
                )
                self.session.add(node)
                await self.session.flush()

                # Create PolitiekeInput
                pi = PolitiekeInput(
                    id=node.id,
                    type=pi_type,
                    referentie=referentie,
                    datum=datum,
                    status=status,
                )
                self.session.add(pi)
                await self.session.flush()

                imported += 1

            except Exception as e:
                errors.append(f"Rij {row_num}: onverwachte fout - {str(e)}")
                skipped += 1

        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    async def import_nodes_csv(self, file_content: bytes) -> ImportResult:
        """Generic node import from CSV: title, node_type, description, status."""
        imported = 0
        skipped = 0
        errors: list[str] = []

        valid_node_types = {
            "dossier",
            "doel",
            "instrument",
            "beleidskader",
            "maatregel",
            "politieke_input",
        }

        text_content = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text_content))

        for row_num, row in enumerate(reader, start=2):
            try:
                title = row.get("title", "").strip()
                node_type = row.get("node_type", "").strip()
                description = row.get("description", "").strip() or None
                status = row.get("status", "").strip() or "actief"

                if not title:
                    errors.append(f"Rij {row_num}: titel ontbreekt")
                    skipped += 1
                    continue

                if node_type not in valid_node_types:
                    errors.append(
                        f"Rij {row_num}: ongeldig node_type '{node_type}' "
                        f"(verwacht: {', '.join(sorted(valid_node_types))})"
                    )
                    skipped += 1
                    continue

                node = CorpusNode(
                    title=title,
                    node_type=node_type,
                    description=description,
                    status=status,
                )
                self.session.add(node)
                await self.session.flush()

                imported += 1

            except Exception as e:
                errors.append(f"Rij {row_num}: onverwachte fout - {str(e)}")
                skipped += 1

        return ImportResult(imported=imported, skipped=skipped, errors=errors)

    async def import_edges_csv(self, file_content: bytes) -> ImportResult:
        """Edge import from CSV.

        Columns: from_node_title, to_node_title,
        edge_type_id, description. Looks up nodes by title.
        """
        from sqlalchemy import select

        imported = 0
        skipped = 0
        errors: list[str] = []

        text_content = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text_content))

        for row_num, row in enumerate(reader, start=2):
            try:
                from_title = row.get("from_node_title", "").strip()
                to_title = row.get("to_node_title", "").strip()
                edge_type_id = row.get("edge_type_id", "").strip()
                description = row.get("description", "").strip() or None

                if not from_title or not to_title:
                    errors.append(
                        f"Rij {row_num}: from_node_title en"
                        " to_node_title zijn verplicht"
                    )
                    skipped += 1
                    continue

                if not edge_type_id:
                    errors.append(f"Rij {row_num}: edge_type_id is verplicht")
                    skipped += 1
                    continue

                # Look up from_node by title
                stmt_from = select(CorpusNode).where(CorpusNode.title == from_title)
                result_from = await self.session.execute(stmt_from)
                from_node = result_from.scalar_one_or_none()

                if from_node is None:
                    errors.append(
                        f"Rij {row_num}: node '{from_title}' niet gevonden"
                    )
                    skipped += 1
                    continue

                # Look up to_node by title
                stmt_to = select(CorpusNode).where(CorpusNode.title == to_title)
                result_to = await self.session.execute(stmt_to)
                to_node = result_to.scalar_one_or_none()

                if to_node is None:
                    errors.append(
                        f"Rij {row_num}: node '{to_title}' niet gevonden"
                    )
                    skipped += 1
                    continue

                # Verify edge_type exists
                from bouwmeester.models.edge_type import EdgeType

                edge_type = await self.session.get(EdgeType, edge_type_id)
                if edge_type is None:
                    errors.append(
                        f"Rij {row_num}: edge_type '{edge_type_id}' niet gevonden"
                    )
                    skipped += 1
                    continue

                edge = Edge(
                    from_node_id=from_node.id,
                    to_node_id=to_node.id,
                    edge_type_id=edge_type_id,
                    description=description,
                )
                self.session.add(edge)
                await self.session.flush()

                imported += 1

            except Exception as e:
                errors.append(f"Rij {row_num}: onverwachte fout - {str(e)}")
                skipped += 1

        return ImportResult(imported=imported, skipped=skipped, errors=errors)
