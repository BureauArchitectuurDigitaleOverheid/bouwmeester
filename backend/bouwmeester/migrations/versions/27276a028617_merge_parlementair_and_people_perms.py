"""merge_parlementair_and_people_perms

Revision ID: 27276a028617
Revises: d2e8f3a91c4b, e3a91c4bd2f7
Create Date: 2026-05-05 07:24:11.305576

Lineariseert de twee alembic heads die ontstaan na merge van #264
(parlementair-permissies, ``d2e8f3a91c4b``) en #265 (people:update,
``e3a91c4bd2f7``). Beide hebben ``c1d4e7a3b9f2`` als down_revision; zonder
deze merge-migratie weigert ``alembic upgrade head`` met "Multiple head
revisions are present".

Geen schema-wijzigingen — puur een revisiebeheers-knooppunt.
"""

from collections.abc import Sequence

revision: str = "27276a028617"
down_revision: str | tuple[str, ...] | None = ("d2e8f3a91c4b", "e3a91c4bd2f7")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
