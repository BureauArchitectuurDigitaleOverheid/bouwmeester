"""Base strategy interface for parliamentary item imports."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date


@dataclass
class FetchedItem:
    """Normalized data from any parliamentary API source."""

    zaak_id: str
    zaak_nummer: str
    titel: str
    onderwerp: str
    datum: date | None = None
    indieners: list[str] = field(default_factory=list)
    document_tekst: str | None = None
    document_url: str | None = None
    bron: str = "tweede_kamer"
    deadline: date | None = None
    ministerie: str | None = None
    extra_data: dict | None = None
    raw_api_response: dict | None = None


class ImportStrategy(ABC):
    """Abstract base for type-specific import behaviour."""

    @property
    @abstractmethod
    def item_type(self) -> str:
        """Identifier stored in ParlementairItem.type (e.g. 'motie')."""
        ...

    @property
    @abstractmethod
    def politieke_input_type(self) -> str:
        """Value for PolitiekeInput.type (e.g. 'motie')."""
        ...

    @property
    def requires_llm(self) -> bool:
        """Whether LLM tag extraction is needed."""
        return True

    @property
    def creates_corpus_node(self) -> bool:
        """Whether a CorpusNode should be created for matched items."""
        return True

    @property
    def supports_ek(self) -> bool:
        """Whether this type exists in the Eerste Kamer API.

        When False, _import_type skips polling EK entirely.
        """
        return True

    @property
    def always_import(self) -> bool:
        """Whether to import even without matched corpus nodes.

        When True, items are imported with status 'imported' and get a
        CorpusNode + review task, but may have zero suggested edges.
        Use for pre-filtered items (e.g. toezeggingen filtered by BZK).
        When False, items without matched nodes are marked 'out_of_scope'.
        """
        return False

    @abstractmethod
    async def fetch_items(
        self,
        client: object,
        since: date | None,
        limit: int,
    ) -> list[FetchedItem]:
        """Fetch items from the parliamentary API."""
        ...

    def calculate_deadline(self, item: FetchedItem) -> date | None:
        """Return a deadline for the review task, or None for default."""
        return item.deadline

    def task_title(self, item: FetchedItem) -> str:
        """Title for the review task."""
        label = self.item_type.replace("_", " ").capitalize()
        return f"Beoordeel {label}: {item.onderwerp}"

    def task_priority(self, item: FetchedItem) -> str:
        """Priority for the review task."""
        return "hoog"

    def notification_title(self, node_title: str) -> str:
        """Title for the notification sent to stakeholders."""
        label = self.item_type.replace("_", " ")
        return f"Nieuw(e) {label}: {node_title}"

    def default_edge_type(self) -> str:
        """Default edge type ID for suggested edges."""
        return "adresseert"

    def politieke_input_status(self, item: FetchedItem) -> str:
        """Status value for the PolitiekeInput record."""
        return "aangenomen"

    def context_hint(self) -> str:
        """Hint passed to LLM for prompt customization."""
        return self.item_type
