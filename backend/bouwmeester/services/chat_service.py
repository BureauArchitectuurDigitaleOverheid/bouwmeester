"""Chat orchestration service — manages tool-calling conversations with VLAM."""

import json
import logging
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
            "description": "Maak een nieuwe taak aan, gekoppeld aan een node.",
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
                        "description": "UUID van de toegewezen persoon (optioneel)",
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
        "create_task": lambda a: f'Taak "{a.get("title", "")}" aanmaken',
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


async def _execute_read_tool(tool_name: str, args: dict, db: AsyncSession) -> str:
    """Execute a read-only tool and return a JSON string result."""
    try:
        if tool_name == "search_nodes":
            from bouwmeester.repositories.search import SearchRepository

            repo = SearchRepository(db)
            query = args.get("query", "")
            node_type = args.get("node_type")
            result_types = ["corpus_node"] if not node_type else ["corpus_node"]
            results = await repo.full_text_search(
                query, result_types=result_types, limit=10
            )
            # Filter by node_type if specified
            if node_type:
                results = [r for r in results if r.get("entity_subtype") == node_type]
            items = [
                {
                    "id": r.get("entity_id"),
                    "title": r.get("title"),
                    "type": r.get("entity_subtype", r.get("entity_type")),
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

        return json.dumps({"error": f"Onbekende tool: {tool_name}"})
    except Exception as e:
        logger.exception("Error executing read tool %s", tool_name)
        return json.dumps({"error": str(e)})


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
            from bouwmeester.repositories.edge import EdgeRepository

            repo = EdgeRepository(db)
            edge = Edge(
                from_node_id=UUID(args["from_node_id"]),
                to_node_id=UUID(args["to_node_id"]),
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
            from bouwmeester.repositories.task import TaskRepository
            from bouwmeester.schema.task import TaskCreate

            repo = TaskRepository(db)
            task_data = {
                "title": args["title"],
                "node_id": UUID(args["node_id"]),
                "description": args.get("description"),
                "priority": args.get("priority", "normaal"),
                "status": "open",
            }
            if args.get("assignee_id"):
                task_data["assignee_id"] = UUID(args["assignee_id"])
            data = TaskCreate(**task_data)
            task = await repo.create(data)
            await db.commit()
            return {
                "success": True,
                "summary": f'Taak "{task.title}" aangemaakt',
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
            from bouwmeester.repositories.tag import TagRepository

            tag_repo = TagRepository(db)
            tag = await tag_repo.get_by_name(args["tag_name"])
            if not tag:
                return {
                    "success": False,
                    "summary": f"Tag '{args['tag_name']}' niet gevonden",
                }
            node_tag = NodeTag(node_id=UUID(args["node_id"]), tag_id=tag.id)
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
            from bouwmeester.repositories.node_stakeholder import (
                NodeStakeholderRepository,
            )

            repo = NodeStakeholderRepository(db)
            await repo.create_stakeholder(
                node_id=UUID(args["node_id"]),
                person_id=UUID(args["person_id"]),
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
    except Exception as e:
        logger.exception("Error executing write tool %s", tool_name)
        await db.rollback()
        return {"success": False, "summary": f"Fout: {e}"}


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
                content = assistant_msg.content or ""
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
                                    "message": "Wacht op bevestiging van de gebruiker.",
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
                    actions.append(
                        ChatAction(
                            tool_name=tool_name,
                            description=f"{tool_name} uitgevoerd",
                            result_summary=result[:200],
                        )
                    )

            # If we have pending writes, stop the loop and return to user
            if has_pending:
                # Get a text response that explains the pending actions
                response2 = await self._llm.chat_with_tools(
                    messages=conv["messages"],
                    tools=[],  # No tools — just generate text
                )
                content = response2.choices[0].message.content or ""
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
            content = response.choices[0].message.content or status_msg
        except Exception:
            content = status_msg

        conv["messages"].append({"role": "assistant", "content": content})

        return ChatMessage(
            role="assistant",
            content=content,
            actions=actions,
        )
