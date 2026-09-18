"""scope active placement unique index by bron

Revision ID: c7b3e1d9a204
Revises: 74c4d614b7f5
Create Date: 2026-09-18

``uq_active_placement`` was a partial unique index on
(person_id, organisatie_eenheid_id) WHERE eind_datum IS NULL, but every sync
service scopes its "does this placement already exist" lookup by ``bron``
(tk_odata, kabinet_yaml, abd_scrape). So the moment one person was active in
one eenheid via two sources the insert blew up with a UniqueViolationError —
which is what killed the daily overheidsorganisaties sync in production.

The collision is legitimate data, not corruption: a Tweede Kamerlid who
becomes bewindspersoon genuinely holds a tk_odata and a kabinet_yaml
placement at the same time. So we widen the index to include ``bron`` rather
than trying to deduplicate across sources, which would need a precedence
rule between feeds that nobody has defined.

Within a single bron the "one active placement" guarantee is unchanged, so
each sync service still cannot duplicate its own rows.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c7b3e1d9a204"
down_revision: str | Sequence[str] | None = "74c4d614b7f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Close pre-existing same-bron duplicates before the narrower index goes
    # on, otherwise CREATE UNIQUE INDEX fails on existing production rows.
    # These are real duplicates (same person, eenheid and source, both open),
    # so keep the oldest open row and close the rest as of today.
    op.execute(
        """
        UPDATE person_organisatie_eenheid p
        SET eind_datum = GREATEST(CURRENT_DATE, p.start_datum)
        WHERE p.eind_datum IS NULL
          AND EXISTS (
              SELECT 1
              FROM person_organisatie_eenheid q
              WHERE q.eind_datum IS NULL
                AND q.person_id = p.person_id
                AND q.organisatie_eenheid_id = p.organisatie_eenheid_id
                AND q.bron = p.bron
                AND (q.start_datum, q.id) < (p.start_datum, p.id)
          )
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_active_placement")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_placement
        ON person_organisatie_eenheid (person_id, organisatie_eenheid_id, bron)
        WHERE eind_datum IS NULL
        """
    )


def downgrade() -> None:
    # Going back to de smallere sleutel betekent dat kruis-bron-duplicaten
    # eerst dicht moeten, anders kan de oude index niet gebouwd worden.
    #
    # Hier wint de NIEUWSTE start_datum, niet de oudste. Een ex-Kamerlid dat
    # bewindspersoon is geworden heeft een oude open tk_odata-rij en een
    # nieuwe open kabinet_yaml-rij; de oudste openhouden zou de actuele
    # ministersplaatsing sluiten en de verlopen zetel bewaren. De volgende
    # kabinet-sync ziet dan geen open kabinet_yaml-rij, voegt er een toe en
    # loopt meteen weer vast op de zojuist herstelde smalle index.
    op.execute(
        """
        UPDATE person_organisatie_eenheid p
        SET eind_datum = GREATEST(CURRENT_DATE, p.start_datum)
        WHERE p.eind_datum IS NULL
          AND EXISTS (
              SELECT 1
              FROM person_organisatie_eenheid q
              WHERE q.eind_datum IS NULL
                AND q.person_id = p.person_id
                AND q.organisatie_eenheid_id = p.organisatie_eenheid_id
                AND (q.start_datum, q.id) > (p.start_datum, p.id)
          )
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_active_placement")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_active_placement
        ON person_organisatie_eenheid (person_id, organisatie_eenheid_id)
        WHERE eind_datum IS NULL
        """
    )
