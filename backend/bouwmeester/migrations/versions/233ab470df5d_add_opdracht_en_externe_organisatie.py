"""add opdracht en externe_organisatie

Revision ID: 233ab470df5d
Revises: 77ef3f614d36
Create Date: 2026-02-16 06:52:43.754992

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = '233ab470df5d'
down_revision: Union[str, None] = '77ef3f614d36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('externe_organisatie',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('naam', sa.String(), nullable=False),
    sa.Column('afkorting', sa.String(), nullable=True),
    sa.Column('type', sa.String(), nullable=False, comment='uitvoeringsorganisatie|zbo|koepelorganisatie|stichting|marktpartij|overig'),
    sa.Column('kvk_nummer', sa.String(), nullable=True),
    sa.Column('website', sa.String(), nullable=True),
    sa.Column('beschrijving', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('opdracht',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('type', sa.String(), nullable=False, comment='opdracht|subsidie'),
    sa.Column('titel', sa.String(), nullable=False),
    sa.Column('beschrijving', sa.Text(), nullable=True),
    sa.Column('begrotingsjaar', sa.Integer(), nullable=False),
    sa.Column('budget', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('gerealiseerd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('kostensoort', sa.String(), nullable=True, comment='investering|exploitatie|gemengd'),
    sa.Column('volgend_jaar_benodigd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('volgend_jaar_aangevraagd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('instrument_id', sa.UUID(), nullable=False),
    sa.Column('opdrachtnemer_id', sa.UUID(), nullable=True),
    sa.Column('opdrachtgever_id', sa.UUID(), nullable=True),
    sa.Column('verantwoordelijke_id', sa.UUID(), nullable=True),
    sa.Column('subsidieregeling', sa.String(), nullable=True),
    sa.Column('beschikking_nummer', sa.String(), nullable=True),
    sa.Column('status', sa.String(), server_default='concept', nullable=False, comment='concept|actief|afgerond|verantwoord|geannuleerd'),
    sa.Column('referentie', sa.String(), nullable=True),
    sa.Column('startdatum', sa.Date(), nullable=True),
    sa.Column('einddatum', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['instrument_id'], ['corpus_node.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['opdrachtgever_id'], ['organisatie_eenheid.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['opdrachtnemer_id'], ['externe_organisatie.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['verantwoordelijke_id'], ['person.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_opdracht_begrotingsjaar'), 'opdracht', ['begrotingsjaar'], unique=False)
    op.create_index(op.f('ix_opdracht_instrument_id'), 'opdracht', ['instrument_id'], unique=False)
    op.create_table('opdracht_node',
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('opdracht_id', sa.UUID(), nullable=False),
    sa.Column('node_id', sa.UUID(), nullable=False),
    sa.Column('relatie_type', sa.String(), server_default='bekostigt', nullable=False, comment='bekostigt|draagt_bij_aan'),
    sa.ForeignKeyConstraint(['node_id'], ['corpus_node.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['opdracht_id'], ['opdracht.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )


    # Seed reference data: externe organisaties
    externe_org = table('externe_organisatie',
        column('naam', sa.String),
        column('afkorting', sa.String),
        column('type', sa.String),
        column('beschrijving', sa.Text),
    )
    op.bulk_insert(externe_org, [
        {'naam': 'Logius', 'afkorting': 'Logius', 'type': 'uitvoeringsorganisatie',
         'beschrijving': 'Beheerorganisatie voor digitale overheidsvoorzieningen zoals DigiD, MijnOverheid en PKIoverheid.'},
        {'naam': 'ICTU', 'afkorting': 'ICTU', 'type': 'stichting',
         'beschrijving': 'ICT-uitvoeringsorganisatie die innovatieve ICT-projecten uitvoert voor de overheid.'},
        {'naam': 'Vereniging van Nederlandse Gemeenten', 'afkorting': 'VNG', 'type': 'koepelorganisatie',
         'beschrijving': 'Behartigt de belangen van alle 342 Nederlandse gemeenten. Ondersteunt gemeenten bij digitale transformatie.'},
        {'naam': 'Geonovum', 'afkorting': 'Geonovum', 'type': 'stichting',
         'beschrijving': 'Ontwikkelt en beheert geo-standaarden voor de overheid.'},
        {'naam': 'RINIS', 'afkorting': 'RINIS', 'type': 'stichting',
         'beschrijving': 'Routeringsinstituut voor (inter)nationale informatiestromen in de sociale zekerheid.'},
        {'naam': 'Rijksdienst voor Identiteitsgegevens', 'afkorting': 'RvIG', 'type': 'uitvoeringsorganisatie',
         'beschrijving': 'Beheerder van de Basisregistratie Personen (BRP) en identiteitsinfrastructuur.'},
        {'naam': 'Kamer van Koophandel', 'afkorting': 'KvK', 'type': 'zbo',
         'beschrijving': 'Beheerder van het Handelsregister en ondersteuner van ondernemers.'},
        {'naam': 'Rijksdienst voor het Wegverkeer', 'afkorting': 'RDW', 'type': 'zbo',
         'beschrijving': 'Beheerder van het kentekenregister en toelating van voertuigen.'},
        {'naam': 'CIBG', 'afkorting': 'CIBG', 'type': 'uitvoeringsorganisatie',
         'beschrijving': 'Uitvoeringsorganisatie voor registers in de zorg, onderwijs en justitie.'},
        {'naam': 'Atos Nederland', 'afkorting': 'Atos', 'type': 'marktpartij',
         'beschrijving': 'IT-dienstverlener, voert opdrachten uit voor diverse overheidssystemen.'},
    ])


def downgrade() -> None:
    op.drop_table('opdracht_node')
    op.drop_index(op.f('ix_opdracht_instrument_id'), table_name='opdracht')
    op.drop_index(op.f('ix_opdracht_begrotingsjaar'), table_name='opdracht')
    op.drop_table('opdracht')
    op.drop_table('externe_organisatie')
