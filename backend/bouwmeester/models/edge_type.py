"""EdgeType model - registry of relation types."""


from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class EdgeType(Base):
    __tablename__ = "edge_type"

    id: Mapped[str] = mapped_column(primary_key=True)
    label_nl: Mapped[str] = mapped_column(nullable=False)
    label_en: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(default=False, server_default="false")
