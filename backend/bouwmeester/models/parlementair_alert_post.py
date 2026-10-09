"""Waar een kamerstuk-alert is gepost, zodat een reactie terug te leiden is.

Zonder deze tabel kan wegklikken niet werken, en dat was ook de stand van
zaken: de constanten voor de reacties stonden
er, `markeer_niet_relevant` bestond en werkte, maar er was geen enkele
aanroeper. De reden zit een laag dieper: `send_channel_message` gaf een
bool terug en gooide het post-id weg, en `_dispatch_reaction_added` zoekt
juist op post-id. De kolom "Weggeklikt" stond daardoor sinds de bouw op
nul en zou daar blijven staan.

Een aparte tabel en geen kolom op het item: één stuk kan in meerdere
kanalen staan (twee initiatieven die dezelfde term volgen, of één
initiatief met twee gekoppelde kanalen), en elk kanaal levert een eigen
post-id op. Een kolom zou er maar één kunnen dragen.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from bouwmeester.core.database import Base


class ParlementairAlertPost(Base):
    """Eén gepost bericht: welk stuk, in welk kanaal, met welk post-id."""

    __tablename__ = "parlementair_alert_post"
    __table_args__ = (
        # Eén bericht per stuk per kanaal. Een tweede poging (een
        # herstart midden in een ronde) hoort geen tweede rij op te
        # leveren die naar een verdwenen post wijst.
        UniqueConstraint(
            "parlementair_item_id", "channel_id", name="uq_alert_post_item_kanaal"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    parlementair_item_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("parlementair_item.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    channel_id: Mapped[str] = mapped_column(String(26), nullable=False)

    # Waar de websocket op zoekt bij een `reaction_added`. Geïndexeerd
    # omdat dat de enige leesrichting is: van reactie naar stuk.
    post_id: Mapped[str] = mapped_column(String(26), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
