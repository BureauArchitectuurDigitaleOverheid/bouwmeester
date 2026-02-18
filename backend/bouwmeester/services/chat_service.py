"""Chat orchestration service — manages tool-calling conversations with VLAM."""

import json
import logging
import re
import time
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.schema.chat import (
    ChatAction,
    ChatMessage,
    PendingAction,
)
from bouwmeester.services.llm.base import BaseLLMService
from bouwmeester.services.llm.prompts import (
    CHAT_SYSTEM_PROMPT,
    build_chat_context_message,
)

logger = logging.getLogger(__name__)

# In-memory conversation store. Each entry: { messages, pending_actions, ts }
_conversations: dict[str, dict] = {}
_CONVERSATION_TTL = 30 * 60  # 30 minutes

# Maximum tool-calling loop iterations to prevent runaway loops.
_MAX_TOOL_ROUNDS = 5


def _cleanup_expired() -> None:
    """Remove conversations older than the TTL."""
    now = time.time()
    expired = [
        k for k, v in _conversations.items() if now - v["ts"] > _CONVERSATION_TTL
    ]
    for k in expired:
        del _conversations[k]


# Regex to strip raw tool-call artefacts from LLM output
_TOOL_CALL_RE = re.compile(
    r"\[TOOL_CALLS?\].*", re.DOTALL
)


def _clean_content(text: str) -> str:
    """Strip raw tool-call artefacts and internal noise from LLM output."""
    # Remove [TOOL_CALLS] blocks that some models emit
    text = _TOOL_CALL_RE.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_READ_TOOLS: dict[str, dict] = {
    "search_nodes": {
        "type": "function",
        "function": {
            "name": "search_nodes",
            "description": (
                "Zoek in het beleidscorpus op"
                " trefwoorden. Geeft nodes terug"
                " met titel, type en ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Zoekterm(en)"},
                    "node_type": {
                        "type": "string",
                        "description": (
                            "Optioneel filter op node-type"
                            " (bijv. dossier, doel,"
                            " instrument)"
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    "get_node": {
        "type": "function",
        "function": {
            "name": "get_node",
            "description": (
                "Haal details op van een specifieke"
                " node (titel, beschrijving,"
                " type, status)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                },
                "required": ["node_id"],
            },
        },
    },
    "get_node_neighbors": {
        "type": "function",
        "function": {
            "name": "get_node_neighbors",
            "description": (
                "Haal de directe buren (verbonden nodes via relaties) op van een node."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                },
                "required": ["node_id"],
            },
        },
    },
    "get_tasks_for_node": {
        "type": "function",
        "function": {
            "name": "get_tasks_for_node",
            "description": "Haal alle taken op die gekoppeld zijn aan een node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                },
                "required": ["node_id"],
            },
        },
    },
    "get_tasks_for_person": {
        "type": "function",
        "function": {
            "name": "get_tasks_for_person",
            "description": (
                "Haal alle taken op die toegewezen zijn aan een persoon."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "UUID van de persoon",
                    },
                },
                "required": ["person_id"],
            },
        },
    },
    "get_overdue_tasks": {
        "type": "function",
        "function": {
            "name": "get_overdue_tasks",
            "description": (
                "Haal alle verlopen taken op"
                " (deadline verstreken, nog niet afgerond)."
                " Optioneel gefilterd op persoon."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee_id": {
                        "type": "string",
                        "description": (
                            "UUID van de persoon (optioneel,"
                            " laat leeg voor alle verlopen taken)"
                        ),
                    },
                },
            },
        },
    },
    "list_tags": {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": "Toon alle beschikbare tags in het systeem.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "list_edge_types": {
        "type": "function",
        "function": {
            "name": "list_edge_types",
            "description": "Toon alle beschikbare relatie-types.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    "search_people": {
        "type": "function",
        "function": {
            "name": "search_people",
            "description": "Zoek personen op naam.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Naam of deel van naam"},
                },
                "required": ["query"],
            },
        },
    },
    "search_organisatie": {
        "type": "function",
        "function": {
            "name": "search_organisatie",
            "description": (
                "Zoek organisatie-eenheden op naam"
                " (ministerie, DG, directie, afdeling, team)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Naam of deel van naam",
                    },
                },
                "required": ["query"],
            },
        },
    },
    "get_organisatie": {
        "type": "function",
        "function": {
            "name": "get_organisatie",
            "description": (
                "Haal details op van een organisatie-eenheid"
                " (naam, type, manager, medewerkers)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "organisatie_id": {
                        "type": "string",
                        "description": "UUID van de organisatie-eenheid",
                    },
                },
                "required": ["organisatie_id"],
            },
        },
    },
    "get_person_summary": {
        "type": "function",
        "function": {
            "name": "get_person_summary",
            "description": (
                "Haal een samenvatting op van een persoon:"
                " naam, organisatie, taken, en betrokken nodes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "person_id": {
                        "type": "string",
                        "description": "UUID van de persoon",
                    },
                },
                "required": ["person_id"],
            },
        },
    },
    "find_path": {
        "type": "function",
        "function": {
            "name": "find_path",
            "description": (
                "Vind het kortste pad via relaties tussen twee nodes"
                " in het beleidsgrafiek."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_node_id": {
                        "type": "string",
                        "description": "UUID van de start-node",
                    },
                    "to_node_id": {
                        "type": "string",
                        "description": "UUID van de eind-node",
                    },
                },
                "required": ["from_node_id", "to_node_id"],
            },
        },
    },
    "find_similar_nodes": {
        "type": "function",
        "function": {
            "name": "find_similar_nodes",
            "description": (
                "Vind nodes met vergelijkbare titels"
                " (handig om duplicaten te ontdekken)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Titel om op te zoeken",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optionele beschrijving voor betere matching",
                    },
                },
                "required": ["title"],
            },
        },
    },
    "list_opdrachten": {
        "type": "function",
        "function": {
            "name": "list_opdrachten",
            "description": (
                "Zoek opdrachten/subsidies. Optioneel"
                " gefilterd op begrotingsjaar, status, of type."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "begrotingsjaar": {
                        "type": "integer",
                        "description": "Begrotingsjaar (bijv. 2025)",
                    },
                    "status": {
                        "type": "string",
                        "description": (
                            "Status: concept, actief,"
                            " afgerond, verantwoord,"
                            " geannuleerd"
                        ),
                    },
                    "type": {
                        "type": "string",
                        "description": "Type: opdracht of subsidie",
                    },
                },
            },
        },
    },
    "get_opdracht": {
        "type": "function",
        "function": {
            "name": "get_opdracht",
            "description": (
                "Haal details op van een opdracht/subsidie"
                " (titel, budget, status, verantwoordelijke)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "opdracht_id": {
                        "type": "string",
                        "description": "UUID van de opdracht",
                    },
                },
                "required": ["opdracht_id"],
            },
        },
    },
    "get_recent_activity": {
        "type": "function",
        "function": {
            "name": "get_recent_activity",
            "description": (
                "Bekijk recente activiteiten/wijzigingen"
                " in het systeem (audit log)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Aantal resultaten (standaard 10, max 20)",
                    },
                },
            },
        },
    },
    "list_parlementair": {
        "type": "function",
        "function": {
            "name": "list_parlementair",
            "description": (
                "Zoek parlementaire items: moties,"
                " kamervragen, toezeggingen, amendementen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "search": {
                        "type": "string",
                        "description": "Zoekterm in titel/onderwerp",
                    },
                    "item_type": {
                        "type": "string",
                        "description": (
                            "Type: motie, kamervraag,"
                            " toezegging, amendement,"
                            " commissiedebat"
                        ),
                    },
                    "status": {
                        "type": "string",
                        "description": "Status: pending, imported, rejected",
                    },
                },
            },
        },
    },
}

_WRITE_TOOLS: dict[str, dict] = {
    "create_node": {
        "type": "function",
        "function": {
            "name": "create_node",
            "description": "Maak een nieuwe node aan in het beleidscorpus.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Titel van de node"},
                    "node_type": {
                        "type": "string",
                        "description": (
                            "Type: dossier, doel,"
                            " instrument, beleidskader,"
                            " maatregel, politieke_input,"
                            " probleem, effect,"
                            " beleidsoptie, bron"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Beschrijving (optioneel)",
                    },
                },
                "required": ["title", "node_type"],
            },
        },
    },
    "update_node": {
        "type": "function",
        "function": {
            "name": "update_node",
            "description": "Wijzig de titel of beschrijving van een bestaande node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                    "title": {
                        "type": "string",
                        "description": "Nieuwe titel (optioneel)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Nieuwe beschrijving (optioneel)",
                    },
                },
                "required": ["node_id"],
            },
        },
    },
    "create_edge": {
        "type": "function",
        "function": {
            "name": "create_edge",
            "description": "Maak een relatie aan tussen twee nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_node_id": {
                        "type": "string",
                        "description": "UUID van de bron-node",
                    },
                    "to_node_id": {
                        "type": "string",
                        "description": "UUID van de doel-node",
                    },
                    "edge_type_id": {
                        "type": "string",
                        "description": (
                            "Relatie-type (bijv."
                            " draagt_bij_aan,"
                            " onderdeel_van,"
                            " verwijst_naar)"
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "Beschrijving van de relatie (optioneel)",
                    },
                },
                "required": ["from_node_id", "to_node_id", "edge_type_id"],
            },
        },
    },
    "create_task": {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": (
                "Maak een nieuwe taak aan, gekoppeld aan een node."
                " Gebruik parent_task_id om een subtaak te maken."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Taaktitel"},
                    "node_id": {
                        "type": "string",
                        "description": "UUID van de gekoppelde node",
                    },
                    "description": {
                        "type": "string",
                        "description": "Beschrijving (optioneel)",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Prioriteit: laag, normaal, hoog, kritiek",
                    },
                    "assignee_id": {
                        "type": "string",
                        "description": (
                            "UUID van de toegewezen persoon (optioneel)"
                        ),
                    },
                    "parent_task_id": {
                        "type": "string",
                        "description": (
                            "UUID van de bovenliggende taak"
                            " om een subtaak te maken (optioneel)"
                        ),
                    },
                },
                "required": ["title", "node_id"],
            },
        },
    },
    "update_task": {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": (
                "Wijzig een bestaande taak (status, prioriteit, titel, beschrijving)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "UUID van de taak"},
                    "title": {
                        "type": "string",
                        "description": "Nieuwe titel (optioneel)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Nieuwe beschrijving (optioneel)",
                    },
                    "status": {
                        "type": "string",
                        "description": "Status: open, in_progress, done, cancelled",
                    },
                    "priority": {
                        "type": "string",
                        "description": "Prioriteit: laag, normaal, hoog, kritiek",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    "add_tag_to_node": {
        "type": "function",
        "function": {
            "name": "add_tag_to_node",
            "description": "Koppel een bestaande tag aan een node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                    "tag_name": {"type": "string", "description": "Naam van de tag"},
                },
                "required": ["node_id", "tag_name"],
            },
        },
    },
    "add_stakeholder": {
        "type": "function",
        "function": {
            "name": "add_stakeholder",
            "description": "Koppel een persoon als stakeholder aan een node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID van de node"},
                    "person_id": {
                        "type": "string",
                        "description": "UUID van de persoon",
                    },
                    "rol": {
                        "type": "string",
                        "description": "Rol: eigenaar, betrokken, adviseur",
                    },
                },
                "required": ["node_id", "person_id", "rol"],
            },
        },
    },
}

ALL_TOOLS = list(_READ_TOOLS.values()) + list(_WRITE_TOOLS.values())
_WRITE_TOOL_NAMES = set(_WRITE_TOOLS.keys())


def _describe_action(tool_name: str, args: dict) -> str:
    """Generate a human-readable Dutch description of a tool call."""
    descriptions = {
        "create_node": lambda a: (
            f'Node "{a.get("title", "")}" ({a.get("node_type", "")}) aanmaken'
        ),
        "update_node": lambda a: f"Node {a.get('node_id', '')[:8]}... bijwerken",
        "create_edge": lambda a: f"Relatie '{a.get('edge_type_id', '')}' aanmaken",
        "create_task": lambda a: (
            f'{"Subtaak" if a.get("parent_task_id") else "Taak"}'
            f' "{a.get("title", "")}" aanmaken'
        ),
        "update_task": lambda a: f"Taak {a.get('task_id', '')[:8]}... bijwerken",
        "add_tag_to_node": lambda a: f"Tag '{a.get('tag_name', '')}' koppelen aan node",
        "add_stakeholder": lambda a: (
            f"Stakeholder ({a.get('rol', '')}) koppelen aan node"
        ),
    }
    fn = descriptions.get(tool_name)
    return fn(args) if fn else f"{tool_name} uitvoeren"


# ---------------------------------------------------------------------------
# Tool execution helpers
# ---------------------------------------------------------------------------


def _task_to_dict(task: object) -> dict:
    """Convert a Task ORM object to a serializable dict."""
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status,
        "priority": getattr(task, "priority", None),
        "deadline": str(task.deadline) if task.deadline else None,
        "assignee": task.assignee.naam if getattr(task, "assignee", None) else None,
        "assignee_id": str(task.assignee_id) if task.assignee_id else None,
        "node_id": str(task.node_id) if task.node_id else None,
    }


async def _execute_read_tool(tool_name: str, args: dict, db: AsyncSession) -> str:
    """Execute a read-only tool and return a JSON string result."""
    try:
        if tool_name == "search_nodes":
            from bouwmeester.repositories.search import SearchRepository

            repo = SearchRepository(db)
            query = args.get("query", "")
            node_type = args.get("node_type")
            results = await repo.full_text_search(
                query, result_types=["corpus_node"], limit=10
            )
            if node_type:
                results = [
                    r for r in results
                    if r.get("subtitle") == node_type
                ]
            items = [
                {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "type": r.get("subtitle"),
                    "score": round(r.get("score", 0), 2),
                }
                for r in results[:10]
            ]
            return json.dumps(
                {"results": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "get_node":
            from bouwmeester.repositories.corpus_node import CorpusNodeRepository

            repo = CorpusNodeRepository(db)
            node = await repo.get(UUID(args["node_id"]))
            if not node:
                return json.dumps({"error": "Node niet gevonden"})
            return json.dumps(
                {
                    "id": str(node.id),
                    "title": node.title,
                    "node_type": node.node_type,
                    "description": (node.description or "")[:500],
                    "status": node.status,
                },
                ensure_ascii=False,
            )

        elif tool_name == "get_node_neighbors":
            from bouwmeester.repositories.corpus_node import CorpusNodeRepository

            repo = CorpusNodeRepository(db)
            data = await repo.get_neighbors(UUID(args["node_id"]))
            if not data.get("node"):
                return json.dumps({"error": "Node niet gevonden"})
            neighbors = [
                {
                    "node_id": str(n["node"].id),
                    "title": n["node"].title,
                    "node_type": n["node"].node_type,
                    "edge_type": n["edge"].edge_type_id,
                }
                for n in data.get("neighbors", [])
            ]
            return json.dumps(
                {"neighbors": neighbors, "count": len(neighbors)}, ensure_ascii=False
            )

        elif tool_name == "get_tasks_for_node":
            from bouwmeester.repositories.task import TaskRepository

            repo = TaskRepository(db)
            tasks = await repo.get_by_node(UUID(args["node_id"]), limit=20)
            items = [_task_to_dict(t) for t in tasks]
            return json.dumps(
                {"tasks": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "get_tasks_for_person":
            from bouwmeester.repositories.task import TaskRepository

            repo = TaskRepository(db)
            tasks = await repo.get_by_assignee(UUID(args["person_id"]), limit=20)
            items = [_task_to_dict(t) for t in tasks]
            return json.dumps(
                {"tasks": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "get_overdue_tasks":
            from bouwmeester.repositories.task import TaskRepository

            repo = TaskRepository(db)
            assignee_id = UUID(args["assignee_id"]) if args.get("assignee_id") else None
            tasks = await repo.get_overdue(assignee_id=assignee_id)
            items = [_task_to_dict(t) for t in tasks[:20]]
            return json.dumps(
                {"tasks": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "list_tags":
            from bouwmeester.repositories.tag import TagRepository

            repo = TagRepository(db)
            tags = await repo.get_all()
            tag_names = [t.name for t in tags[:100]]
            return json.dumps(
                {"tags": tag_names, "count": len(tag_names)}, ensure_ascii=False
            )

        elif tool_name == "list_edge_types":
            from bouwmeester.repositories.edge_type import EdgeTypeRepository

            repo = EdgeTypeRepository(db)
            types = await repo.get_all()
            type_ids = [t.id for t in types]
            return json.dumps({"edge_types": type_ids}, ensure_ascii=False)

        elif tool_name == "search_people":
            from bouwmeester.repositories.person import PersonRepository

            repo = PersonRepository(db)
            people = await repo.search(args.get("query", ""), limit=10)
            items = [{"id": str(p.id), "naam": p.naam} for p in people]
            return json.dumps(
                {"results": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "search_organisatie":
            from bouwmeester.repositories.organisatie_eenheid import (
                OrganisatieEenheidRepository,
            )

            repo = OrganisatieEenheidRepository(db)
            units = await repo.search(args.get("query", ""), limit=10)
            items = [
                {
                    "id": str(u.id),
                    "naam": u.naam,
                    "type": u.type,
                }
                for u in units
            ]
            return json.dumps(
                {"results": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "get_organisatie":
            from bouwmeester.repositories.organisatie_eenheid import (
                OrganisatieEenheidRepository,
            )

            repo = OrganisatieEenheidRepository(db)
            unit = await repo.get(UUID(args["organisatie_id"]))
            if not unit:
                return json.dumps({"error": "Organisatie-eenheid niet gevonden"})
            personen = await repo.get_personen(unit.id)
            return json.dumps(
                {
                    "id": str(unit.id),
                    "naam": unit.naam,
                    "type": unit.type,
                    "manager": (
                        unit.manager.naam
                        if getattr(unit, "manager", None)
                        else None
                    ),
                    "manager_id": str(unit.manager_id) if unit.manager_id else None,
                    "parent_id": str(unit.parent_id) if unit.parent_id else None,
                    "medewerkers": [
                        {"id": str(p.id), "naam": p.naam} for p in personen[:20]
                    ],
                    "aantal_medewerkers": len(personen),
                },
                ensure_ascii=False,
            )

        elif tool_name == "get_person_summary":
            from sqlalchemy import select as sa_select

            from bouwmeester.models.organisatie_eenheid import (
                OrganisatieEenheid,
            )
            from bouwmeester.models.person_organisatie import (
                PersonOrganisatieEenheid,
            )
            from bouwmeester.repositories.person import PersonRepository
            from bouwmeester.repositories.task import TaskRepository

            person_repo = PersonRepository(db)
            person = await person_repo.get(UUID(args["person_id"]))
            if not person:
                return json.dumps({"error": "Persoon niet gevonden"})

            task_repo = TaskRepository(db)
            tasks = await task_repo.get_by_assignee(
                person.id, limit=10
            )
            open_tasks = [
                t for t in tasks
                if t.status not in ("done", "cancelled")
            ]

            # Find current org unit via active placement
            org_name = None
            org_id = None
            stmt = (
                sa_select(OrganisatieEenheid)
                .join(PersonOrganisatieEenheid)
                .where(
                    PersonOrganisatieEenheid.person_id
                    == person.id,
                    PersonOrganisatieEenheid.eind_datum.is_(
                        None
                    ),
                )
                .limit(1)
            )
            org_result = await db.execute(stmt)
            org_unit = org_result.scalar_one_or_none()
            if org_unit:
                org_name = org_unit.naam
                org_id = str(org_unit.id)

            result = {
                "id": str(person.id),
                "naam": person.naam,
                "organisatie_eenheid": org_name,
                "organisatie_eenheid_id": org_id,
                "open_taken": [
                    _task_to_dict(t) for t in open_tasks[:5]
                ],
                "aantal_open_taken": len(open_tasks),
            }
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "find_path":
            from bouwmeester.repositories.graph import GraphRepository

            repo = GraphRepository(db)
            path = await repo.find_path(
                UUID(args["from_node_id"]), UUID(args["to_node_id"])
            )
            if not path:
                return json.dumps(
                    {"path": [], "message": "Geen pad gevonden tussen deze nodes"}
                )
            steps = [
                {
                    "node_id": str(step.get("node_id", "")),
                    "title": step.get("node_title", ""),
                    "node_type": step.get("node_type", ""),
                    "edge_type": step.get("edge_type_id"),
                }
                for step in path
            ]
            return json.dumps(
                {"path": steps, "length": len(steps)}, ensure_ascii=False
            )

        elif tool_name == "find_similar_nodes":
            from bouwmeester.repositories.search import SearchRepository

            repo = SearchRepository(db)
            results = await repo.find_similar_nodes(
                title=args["title"],
                description=args.get("description"),
                limit=5,
            )
            items = [
                {
                    "id": str(r["id"]),
                    "title": r["title"],
                    "node_type": r["node_type"],
                    "similarity": r.get("similarity", 0),
                }
                for r in results
            ]
            return json.dumps(
                {"results": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "list_opdrachten":
            from bouwmeester.repositories.opdracht import OpdrachtRepository

            repo = OpdrachtRepository(db)
            opdrachten = await repo.get_all(
                limit=15,
                begrotingsjaar=args.get("begrotingsjaar"),
                status=args.get("status"),
                type=args.get("type"),
            )
            items = [
                {
                    "id": str(o.id),
                    "titel": o.titel,
                    "type": o.type,
                    "status": o.status,
                    "begrotingsjaar": o.begrotingsjaar,
                    "budget": str(o.budget) if o.budget else None,
                    "gerealiseerd": str(o.gerealiseerd) if o.gerealiseerd else None,
                }
                for o in opdrachten
            ]
            return json.dumps(
                {"opdrachten": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "get_opdracht":
            from bouwmeester.repositories.opdracht import OpdrachtRepository

            repo = OpdrachtRepository(db)
            o = await repo.get(UUID(args["opdracht_id"]))
            if not o:
                return json.dumps({"error": "Opdracht niet gevonden"})
            return json.dumps(
                {
                    "id": str(o.id),
                    "titel": o.titel,
                    "type": o.type,
                    "status": o.status,
                    "begrotingsjaar": o.begrotingsjaar,
                    "budget": str(o.budget) if o.budget else None,
                    "gerealiseerd": str(o.gerealiseerd) if o.gerealiseerd else None,
                    "beschrijving": (o.beschrijving or "")[:300],
                    "verantwoordelijke": (
                        o.verantwoordelijke.naam
                        if getattr(o, "verantwoordelijke", None)
                        else None
                    ),
                    "verantwoordelijke_id": (
                        str(o.verantwoordelijke_id) if o.verantwoordelijke_id else None
                    ),
                    "instrument_id": str(o.instrument_id) if o.instrument_id else None,
                },
                ensure_ascii=False,
            )

        elif tool_name == "get_recent_activity":
            from bouwmeester.repositories.activity import ActivityRepository

            repo = ActivityRepository(db)
            limit = min(int(args.get("limit", 10)), 20)
            activities = await repo.get_recent(limit=limit)
            items = [
                {
                    "event_type": a.event_type,
                    "actor": a.actor.naam if getattr(a, "actor", None) else None,
                    "node_id": str(a.node_id) if a.node_id else None,
                    "task_id": str(a.task_id) if a.task_id else None,
                    "details": a.details if a.details else None,
                    "timestamp": a.created_at.isoformat() if a.created_at else None,
                }
                for a in activities
            ]
            return json.dumps(
                {"activities": items, "count": len(items)}, ensure_ascii=False
            )

        elif tool_name == "list_parlementair":
            from bouwmeester.repositories.parlementair_item import (
                ParlementairItemRepository,
            )

            repo = ParlementairItemRepository(db)
            items_raw = await repo.get_all(
                search=args.get("search"),
                item_type=args.get("item_type"),
                status=args.get("status"),
                limit=10,
            )
            items = [
                {
                    "id": str(pi.id),
                    "titel": pi.titel,
                    "type": pi.type,
                    "status": pi.status,
                    "onderwerp": (pi.onderwerp or "")[:200],
                }
                for pi in items_raw
            ]
            return json.dumps(
                {"items": items, "count": len(items)}, ensure_ascii=False
            )

        return json.dumps({"error": f"Onbekende tool: {tool_name}"})
    except ValueError:
        return json.dumps(
            {"error": "Ongeldig ID-formaat. Gebruik een geldig UUID."}
        )
    except Exception:
        logger.exception("Error executing read tool %s", tool_name)
        return json.dumps(
            {"error": "Er is een fout opgetreden bij het ophalen van data."}
        )


async def _execute_write_tool(tool_name: str, args: dict, db: AsyncSession) -> dict:
    """Execute a write tool. Returns { success, summary, entity_id, entity_type }."""
    try:
        if tool_name == "create_node":
            from bouwmeester.repositories.corpus_node import CorpusNodeRepository
            from bouwmeester.schema.corpus_node import CorpusNodeCreate

            repo = CorpusNodeRepository(db)
            data = CorpusNodeCreate(
                title=args["title"],
                node_type=args["node_type"],
                description=args.get("description"),
            )
            node = await repo.create(data)
            await db.commit()
            return {
                "success": True,
                "summary": f'Node "{node.title}" ({node.node_type}) aangemaakt',
                "entity_id": str(node.id),
                "entity_type": "node",
            }

        elif tool_name == "update_node":
            from bouwmeester.repositories.corpus_node import CorpusNodeRepository
            from bouwmeester.schema.corpus_node import CorpusNodeUpdate

            repo = CorpusNodeRepository(db)
            update_data: dict = {}
            if "title" in args:
                update_data["title"] = args["title"]
            if "description" in args:
                update_data["description"] = args["description"]
            data = CorpusNodeUpdate(**update_data)
            node = await repo.update(UUID(args["node_id"]), data)
            if not node:
                return {"success": False, "summary": "Node niet gevonden"}
            await db.commit()
            return {
                "success": True,
                "summary": f'Node "{node.title}" bijgewerkt',
                "entity_id": str(node.id),
                "entity_type": "node",
            }

        elif tool_name == "create_edge":
            from bouwmeester.models.edge import Edge
            from bouwmeester.repositories.corpus_node import (
                CorpusNodeRepository,
            )

            node_repo = CorpusNodeRepository(db)

            from_node = await node_repo.get(
                UUID(args["from_node_id"])
            )
            if not from_node:
                return {
                    "success": False,
                    "summary": "Bron-node niet gevonden.",
                }

            to_node = await node_repo.get(
                UUID(args["to_node_id"])
            )
            if not to_node:
                return {
                    "success": False,
                    "summary": "Doel-node niet gevonden.",
                }

            edge = Edge(
                from_node_id=from_node.id,
                to_node_id=to_node.id,
                edge_type_id=args["edge_type_id"],
                description=args.get("description"),
            )
            db.add(edge)
            await db.flush()
            await db.commit()
            return {
                "success": True,
                "summary": f"Relatie '{edge.edge_type_id}' aangemaakt",
                "entity_id": str(edge.id),
                "entity_type": "edge",
            }

        elif tool_name == "create_task":
            from bouwmeester.repositories.corpus_node import CorpusNodeRepository
            from bouwmeester.repositories.person import PersonRepository
            from bouwmeester.repositories.task import TaskRepository
            from bouwmeester.schema.task import TaskCreate

            # Validate node exists
            node_repo = CorpusNodeRepository(db)
            node = await node_repo.get(UUID(args["node_id"]))
            if not node:
                return {
                    "success": False,
                    "summary": "Node niet gevonden",
                }

            # Validate assignee exists if provided
            if args.get("assignee_id"):
                person_repo = PersonRepository(db)
                person = await person_repo.get(
                    UUID(args["assignee_id"])
                )
                if not person:
                    return {
                        "success": False,
                        "summary": (
                            "Persoon niet gevonden."
                            " Gebruik search_people om"
                            " de juiste persoon te vinden."
                        ),
                    }

            # Validate parent task exists if provided
            if args.get("parent_task_id"):
                parent_repo = TaskRepository(db)
                parent_task = await parent_repo.get(
                    UUID(args["parent_task_id"])
                )
                if not parent_task:
                    return {
                        "success": False,
                        "summary": (
                            "Bovenliggende taak niet"
                            " gevonden. Gebruik"
                            " get_tasks_for_node om de"
                            " juiste taak te vinden."
                        ),
                    }

            repo = TaskRepository(db)
            task_data: dict = {
                "title": args["title"],
                "node_id": UUID(args["node_id"]),
                "description": args.get("description"),
                "priority": args.get("priority", "normaal"),
                "status": "open",
            }
            if args.get("assignee_id"):
                task_data["assignee_id"] = UUID(args["assignee_id"])
            if args.get("parent_task_id"):
                task_data["parent_id"] = UUID(
                    args["parent_task_id"]
                )
            data = TaskCreate(**task_data)
            task = await repo.create(data)
            await db.commit()
            is_subtask = bool(args.get("parent_task_id"))
            label = "Subtaak" if is_subtask else "Taak"
            return {
                "success": True,
                "summary": f'{label} "{task.title}" aangemaakt',
                "entity_id": str(task.id),
                "entity_type": "task",
            }

        elif tool_name == "update_task":
            from bouwmeester.repositories.task import TaskRepository
            from bouwmeester.schema.task import TaskUpdate

            repo = TaskRepository(db)
            update_data = {}
            for field in ("title", "description", "status", "priority"):
                if field in args and args[field] is not None:
                    update_data[field] = args[field]
            data = TaskUpdate(**update_data)
            task = await repo.update(UUID(args["task_id"]), data)
            if not task:
                return {"success": False, "summary": "Taak niet gevonden"}
            await db.commit()
            return {
                "success": True,
                "summary": f'Taak "{task.title}" bijgewerkt',
                "entity_id": str(task.id),
                "entity_type": "task",
            }

        elif tool_name == "add_tag_to_node":
            from bouwmeester.models.tag import NodeTag
            from bouwmeester.repositories.corpus_node import (
                CorpusNodeRepository,
            )
            from bouwmeester.repositories.tag import TagRepository

            node_repo = CorpusNodeRepository(db)
            node = await node_repo.get(UUID(args["node_id"]))
            if not node:
                return {
                    "success": False,
                    "summary": "Node niet gevonden.",
                }

            tag_repo = TagRepository(db)
            tag = await tag_repo.get_by_name(args["tag_name"])
            if not tag:
                return {
                    "success": False,
                    "summary": (
                        f"Tag '{args['tag_name']}'"
                        " niet gevonden."
                        " Gebruik list_tags om"
                        " beschikbare tags te zien."
                    ),
                }
            node_tag = NodeTag(node_id=node.id, tag_id=tag.id)
            db.add(node_tag)
            await db.flush()
            await db.commit()
            return {
                "success": True,
                "summary": f"Tag '{tag.name}' gekoppeld aan node",
                "entity_id": args["node_id"],
                "entity_type": "tag",
            }

        elif tool_name == "add_stakeholder":
            from bouwmeester.repositories.corpus_node import (
                CorpusNodeRepository,
            )
            from bouwmeester.repositories.node_stakeholder import (
                NodeStakeholderRepository,
            )
            from bouwmeester.repositories.person import PersonRepository

            node_repo = CorpusNodeRepository(db)
            node = await node_repo.get(UUID(args["node_id"]))
            if not node:
                return {
                    "success": False,
                    "summary": "Node niet gevonden.",
                }

            person_repo = PersonRepository(db)
            person = await person_repo.get(
                UUID(args["person_id"])
            )
            if not person:
                return {
                    "success": False,
                    "summary": (
                        "Persoon niet gevonden."
                        " Gebruik search_people om"
                        " de juiste persoon te vinden."
                    ),
                }

            repo = NodeStakeholderRepository(db)
            await repo.create_stakeholder(
                node_id=node.id,
                person_id=person.id,
                rol=args["rol"],
            )
            await db.commit()
            return {
                "success": True,
                "summary": f"Stakeholder ({args['rol']}) gekoppeld aan node",
                "entity_id": args["node_id"],
                "entity_type": "node",
            }

        return {"success": False, "summary": f"Onbekende tool: {tool_name}"}
    except ValueError:
        return {
            "success": False,
            "summary": "Ongeldig ID-formaat. Gebruik een geldig UUID.",
        }
    except Exception:
        logger.exception("Error executing write tool %s", tool_name)
        await db.rollback()
        return {
            "success": False,
            "summary": (
                "Er is een fout opgetreden bij het"
                " uitvoeren van deze actie."
                " Probeer het opnieuw."
            ),
        }


# ---------------------------------------------------------------------------
# Main chat orchestration
# ---------------------------------------------------------------------------


class ChatService:
    """Orchestrates multi-turn chat with tool calling."""

    def __init__(self, llm: BaseLLMService, db: AsyncSession) -> None:
        self._llm = llm
        self._db = db

    async def send_message(
        self,
        message: str,
        conversation_id: str | None = None,
        context: dict | None = None,
    ) -> tuple[str, ChatMessage]:
        """Process a user message and return (conversation_id, response_message)."""
        _cleanup_expired()

        # Get or create conversation
        if conversation_id and conversation_id in _conversations:
            conv = _conversations[conversation_id]
        else:
            conversation_id = str(uuid.uuid4())
            conv = {
                "messages": [{"role": "system", "content": CHAT_SYSTEM_PROMPT}],
                "pending_actions": {},
                "ts": time.time(),
            }
            _conversations[conversation_id] = conv

        # Add context awareness
        context_msg = build_chat_context_message(context)
        if context_msg:
            # Update system message with context
            system_content = CHAT_SYSTEM_PROMPT + "\n\nHUIDIGE CONTEXT:\n" + context_msg
            conv["messages"][0] = {"role": "system", "content": system_content}

        # Add user message
        conv["messages"].append({"role": "user", "content": message})
        conv["ts"] = time.time()

        # Tool-calling loop
        actions: list[ChatAction] = []
        pending_actions: list[PendingAction] = []

        for _ in range(_MAX_TOOL_ROUNDS):
            response = await self._llm.chat_with_tools(
                messages=conv["messages"],
                tools=ALL_TOOLS,
            )
            choice = response.choices[0]
            assistant_msg = choice.message

            # If no tool calls, we have the final text response
            if not assistant_msg.tool_calls:
                content = _clean_content(assistant_msg.content or "")
                conv["messages"].append({"role": "assistant", "content": content})
                break

            # Process tool calls
            # Add assistant message with tool calls to history
            conv["messages"].append(
                {
                    "role": "assistant",
                    "content": assistant_msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in assistant_msg.tool_calls
                    ],
                }
            )

            has_pending = False
            for tc in assistant_msg.tool_calls:
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                if tool_name in _WRITE_TOOL_NAMES:
                    # Queue for confirmation
                    action_id = str(uuid.uuid4())
                    pending = PendingAction(
                        action_id=action_id,
                        tool_name=tool_name,
                        arguments=args,
                        description=_describe_action(tool_name, args),
                    )
                    pending_actions.append(pending)
                    conv["pending_actions"][action_id] = {
                        "tool_name": tool_name,
                        "arguments": args,
                        "tool_call_id": tc.id,
                    }
                    # Add a placeholder tool result
                    conv["messages"].append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(
                                {
                                    "status": "pending_confirmation",
                                    "message": (
                                        "Deze actie is NOG NIET"
                                        " uitgevoerd. De gebruiker"
                                        " moet eerst bevestigen via"
                                        " een knop in de interface."
                                    ),
                                }
                            ),
                        }
                    )
                    has_pending = True
                else:
                    # Execute read tool immediately
                    result = await _execute_read_tool(tool_name, args, self._db)
                    conv["messages"].append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                    # Read actions are internal — don't surface to user

            # If we have pending writes, stop the loop and return to user
            if has_pending:
                # Get a text response that explains the pending actions
                response2 = await self._llm.chat_with_tools(
                    messages=conv["messages"],
                    tools=[],  # No tools — just generate text
                )
                content = _clean_content(
                    response2.choices[0].message.content or ""
                )
                conv["messages"].append({"role": "assistant", "content": content})
                break
        else:
            # If we exhausted the loop
            content = (
                "Ik kon het verzoek niet volledig"
                " verwerken. Probeer het opnieuw"
                " met een specifiekere vraag."
            )
            conv["messages"].append({"role": "assistant", "content": content})

        return conversation_id, ChatMessage(
            role="assistant",
            content=content,
            actions=actions,
            pending_actions=pending_actions,
        )

    async def confirm_action(
        self,
        conversation_id: str,
        action_id: str,
        approved: bool,
    ) -> ChatMessage:
        """Confirm or reject a pending write action."""
        conv = _conversations.get(conversation_id)
        if not conv:
            return ChatMessage(
                role="assistant",
                content="Conversatie niet gevonden of verlopen.",
            )

        pending = conv["pending_actions"].pop(action_id, None)
        if not pending:
            return ChatMessage(
                role="assistant",
                content="Actie niet gevonden of al verwerkt.",
            )

        conv["ts"] = time.time()
        actions: list[ChatAction] = []

        if approved:
            result = await _execute_write_tool(
                pending["tool_name"],
                pending["arguments"],
                self._db,
            )
            actions.append(
                ChatAction(
                    tool_name=pending["tool_name"],
                    description=result.get("summary", ""),
                    result_summary=result.get("summary", ""),
                    entity_id=result.get("entity_id"),
                    entity_type=result.get("entity_type"),
                )
            )
            status_msg = (
                result["summary"]
                if result["success"]
                else f"Mislukt: {result['summary']}"
            )
        else:
            desc = _describe_action(pending["tool_name"], pending["arguments"])
            status_msg = f"{desc} — geannuleerd door gebruiker"

        # Add result to conversation and get final response
        conv["messages"].append(
            {
                "role": "user",
                "content": (
                    f"[Actie {'bevestigd' if approved else 'geannuleerd'}] {status_msg}"
                ),
            }
        )

        try:
            response = await self._llm.chat_with_tools(
                messages=conv["messages"],
                tools=[],
            )
            content = _clean_content(
                response.choices[0].message.content or status_msg
            )
        except Exception:
            content = status_msg

        conv["messages"].append({"role": "assistant", "content": content})

        return ChatMessage(
            role="assistant",
            content=content,
            actions=actions,
        )
