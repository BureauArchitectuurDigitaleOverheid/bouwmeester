# Import all models here so that Base.metadata is populated
# and Alembic can detect them for autogenerate.

from bouwmeester.models.absence import Absence  # noqa: F401
from bouwmeester.models.activity import Activity  # noqa: F401
from bouwmeester.models.beleidskader import Beleidskader  # noqa: F401
from bouwmeester.models.beleidsoptie import Beleidsoptie  # noqa: F401
from bouwmeester.models.corpus_node import CorpusNode  # noqa: F401
from bouwmeester.models.doel import Doel  # noqa: F401
from bouwmeester.models.dossier import Dossier  # noqa: F401
from bouwmeester.models.edge import Edge  # noqa: F401
from bouwmeester.models.edge_type import EdgeType  # noqa: F401
from bouwmeester.models.effect import Effect  # noqa: F401
from bouwmeester.models.instrument import Instrument  # noqa: F401
from bouwmeester.models.maatregel import Maatregel  # noqa: F401
from bouwmeester.models.mention import Mention  # noqa: F401
from bouwmeester.models.motie_import import MotieImport, SuggestedEdge  # noqa: F401
from bouwmeester.models.node_stakeholder import NodeStakeholder  # noqa: F401
from bouwmeester.models.notification import Notification  # noqa: F401
from bouwmeester.models.organisatie_eenheid import OrganisatieEenheid  # noqa: F401
from bouwmeester.models.person import Person  # noqa: F401
from bouwmeester.models.politieke_input import PolitiekeInput  # noqa: F401
from bouwmeester.models.probleem import Probleem  # noqa: F401
from bouwmeester.models.tag import NodeTag, Tag  # noqa: F401
from bouwmeester.models.task import Task  # noqa: F401
from bouwmeester.models.team import Team, TeamMember  # noqa: F401

__all__ = [
    "Absence",
    "Activity",
    "Beleidskader",
    "Beleidsoptie",
    "CorpusNode",
    "Doel",
    "Dossier",
    "Edge",
    "EdgeType",
    "Effect",
    "Instrument",
    "Maatregel",
    "Mention",
    "MotieImport",
    "NodeStakeholder",
    "NodeTag",
    "Notification",
    "OrganisatieEenheid",
    "Person",
    "PolitiekeInput",
    "Probleem",
    "SuggestedEdge",
    "Tag",
    "Task",
    "Team",
    "TeamMember",
]
