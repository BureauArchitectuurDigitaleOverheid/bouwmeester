"""Where an import that follows a feed has got to.

A strategy that follows a feed (tkconv, news) imports what appeared after
the newest thing it has handled: its watermark. That used to live in the
memory of the worker only, so every restart put it back to "now" and
whatever appeared between the last round and the restart was never
imported. With a deploy a week that is a rare miss; with fifteen deploys
in two days, most of them in office hours when documents appear, it cost
real alerts. One row per source keeps it across restarts.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class ImportWatermerk(Base):
    __tablename__ = "import_watermerk"

    # The item type of the strategy ("tkconv_document", "nieuws").
    bron: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Everything that appeared later than this still has to be imported.
    tijdstip: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
