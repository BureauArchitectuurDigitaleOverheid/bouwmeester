"""API-routes voor parlementaire abonnementen op zoektermen.

Autorisatie loopt via toegang tot het initiatief, niet via een apart
beheerdersrecht. Wie een initiatief mag zien, mag bepalen wat het volgt:
een zoekterm toevoegen is geen systeembeheer maar onderdeel van het werk
aan dat initiatief. Een beheerdersrecht zou betekenen dat elke nieuwe term
langs een beheerder moet, en dan gebeurt het niet.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bouwmeester.core.auth import OptionalUser
from bouwmeester.core.database import get_db
from bouwmeester.core.initiatief_context import (
    InitiatiefContext,
    get_initiatief_context,
)
from bouwmeester.core.rate_limit import InMemoryRateLimiter
from bouwmeester.models.initiatief import Initiatief
from bouwmeester.models.parlementair_abonnement import (
    SCOPE_INITIATIEF,
    ParlementairAbonnement,
)
from bouwmeester.repositories.parlementair_abonnement import (
    ParlementairAbonnementRepository,
)
from bouwmeester.schema.parlementair_abonnement import (
    AbonnementCreate,
    AbonnementMetTellingResponse,
    AbonnementUpdate,
    SuggestieResponse,
)
from bouwmeester.services.activity_service import log_activity
from bouwmeester.services.llm import get_llm_service
from bouwmeester.services.tkconv_client import TkconvClient
from bouwmeester.services.zoekterm_suggesties import stel_voor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/initiatieven", tags=["parlementair-abonnement"])

# Suggesties kosten een LLM-call plus negen verzoeken aan berthub.eu, een
# privéserver zonder SLA. Vijf per vijf minuten is ruim voor iemand die
# zoektermen aan het instellen is, en smal genoeg om er geen lus van te
# kunnen maken. Dezelfde waarden als de access-request-limiter.
_suggestie_limiter = InMemoryRateLimiter(window=300, max_requests=5)


async def _require_initiatief_toegang(
    db: AsyncSession, ctx: InitiatiefContext, initiatief_id: UUID
) -> Initiatief:
    """Geef het initiatief terug, of 404 als de gebruiker het niet mag zien.

    Bewust 404 en geen 403: het bestaan van een initiatief is zelf al
    informatie.
    """
    if not ctx.is_authenticated:
        raise HTTPException(status_code=401, detail="Niet ingelogd")

    initiatief = await db.get(Initiatief, initiatief_id)
    if initiatief is None:
        raise HTTPException(status_code=404, detail="Initiatief niet gevonden")

    if not ctx.is_admin and initiatief_id not in ctx.visible_initiatief_ids:
        raise HTTPException(status_code=404, detail="Initiatief niet gevonden")
    return initiatief


def _onderwerp_van(initiatief: Initiatief) -> str:
    """Waar dit initiatief over gaat, als platte tekst voor de prompt.

    De beschrijving staat als tiptap-JSON in de database; zonder conversie
    zou de prompt een documentboom te lezen krijgen in plaats van een zin.
    """
    from bouwmeester.utils.tiptap import tiptap_to_plain

    beschrijving = (tiptap_to_plain(initiatief.beschrijving) or "").strip()
    if beschrijving:
        return f"{initiatief.naam}. {beschrijving[:600]}"
    return initiatief.naam


def _hoort_bij(abonnement: ParlementairAbonnement | None, initiatief_id: UUID) -> bool:
    """Hoort dit abonnement bij dít initiatief?

    `scope_id` is polymorf en draagt geen FK, dus het kan ook een `lead.id`
    zijn. De sleutel is het paar (scope_type, scope_id); alleen op
    `scope_id` vergelijken laat de helft daarvan liggen.
    """
    return (
        abonnement is not None
        and abonnement.scope_type == SCOPE_INITIATIEF
        and abonnement.scope_id == initiatief_id
    )


def _met_telling(
    abonnement: ParlementairAbonnement, tellingen: dict[UUID, int]
) -> AbonnementMetTellingResponse:
    response = AbonnementMetTellingResponse.model_validate(abonnement)
    response.treffers = tellingen.get(abonnement.id, 0)
    return response


@router.get(
    "/{initiatief_id}/abonnementen",
    response_model=list[AbonnementMetTellingResponse],
)
async def list_abonnementen(
    initiatief_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalUser = None,
    ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[AbonnementMetTellingResponse]:
    """Welke zoektermen dit initiatief volgt, met wat ze opleveren."""
    await _require_initiatief_toegang(db, ctx, initiatief_id)

    repo = ParlementairAbonnementRepository(db)
    abonnementen = await repo.list_for_scope(SCOPE_INITIATIEF, initiatief_id)
    tellingen = await repo.telling_per_abonnement(SCOPE_INITIATIEF, initiatief_id)
    return [_met_telling(a, tellingen) for a in abonnementen]


@router.post(
    "/{initiatief_id}/abonnementen",
    response_model=AbonnementMetTellingResponse,
    status_code=201,
)
async def create_abonnement(
    initiatief_id: UUID,
    payload: AbonnementCreate,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalUser = None,
    ctx: InitiatiefContext = Depends(get_initiatief_context),
    actor_id: UUID | None = None,
) -> AbonnementMetTellingResponse:
    """Volg een nieuwe zoekterm voor dit initiatief."""
    await _require_initiatief_toegang(db, ctx, initiatief_id)

    repo = ParlementairAbonnementRepository(db)
    bestaand = await repo.get_by_term(SCOPE_INITIATIEF, initiatief_id, payload.term)
    if bestaand is not None:
        # Een gedeactiveerde term weer aanzetten in plaats van een
        # duplicaat maken: de telling blijft dan intact.
        if not bestaand.actief:
            bestaand.actief = True
            await db.commit()
            await db.refresh(bestaand)
            tellingen = await repo.telling_per_abonnement(
                SCOPE_INITIATIEF, initiatief_id
            )
            return _met_telling(bestaand, tellingen)
        raise HTTPException(
            status_code=409, detail=f"'{bestaand.term}' wordt al gevolgd"
        )

    abonnement = await repo.create(
        scope_type=SCOPE_INITIATIEF,
        scope_id=initiatief_id,
        term=payload.term,
        is_frase=payload.is_frase,
        notitie=payload.notitie,
        created_by_id=current_user.id if current_user else None,
    )
    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.abonnement_toegevoegd",
        details={"initiatief_id": str(initiatief_id), "term": abonnement.term},
    )
    try:
        await db.commit()
    except IntegrityError:
        # `get_by_term` en de insert zijn niet atomair: twee snelle klikken
        # op "Volgen" zien allebei niets bestaan en botsen daarna op
        # `uq_abonnement_scope_term`. Dat is dezelfde situatie als hierboven,
        # dus hetzelfde antwoord — niet een 500.
        await db.rollback()
        raise HTTPException(
            status_code=409, detail=f"'{payload.term}' wordt al gevolgd"
        ) from None
    await db.refresh(abonnement)

    tellingen = await repo.telling_per_abonnement(SCOPE_INITIATIEF, initiatief_id)
    return _met_telling(abonnement, tellingen)


@router.post(
    "/{initiatief_id}/abonnementen/suggesties",
    response_model=list[SuggestieResponse],
)
async def suggereer_zoektermen(
    initiatief_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalUser = None,
    ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> list[SuggestieResponse]:
    """Stel extra zoektermen voor bij wat dit initiatief al volgt.

    Het taalmodel doet het voorstel, daarna meet dit endpoint bij de bron
    hoeveel treffers elke term werkelijk oplevert en hoeveel daarvan nieuw
    zijn. Die getallen gaan mee naar de gebruiker, want zonder meting is
    een suggestie een gok: bij een test leverden vijf van de zes
    voorgestelde termen nul stukken op.

    POST en geen GET: het kost een LLM-call en een handvol verzoeken aan
    een server van derden, dus het hoort een bewuste handeling te zijn en
    niet iets wat een pagina bij het laden doet.
    """
    initiatief = await _require_initiatief_toegang(db, ctx, initiatief_id)

    # Eén aanroep kost een LLM-call plus negen verzoeken aan een server
    # van derden. Zonder limiet kan iedereen met toegang tot één
    # initiatief dat in een lus doen, en dat komt bij berthub.eu terecht.
    _suggestie_limiter.check(request)

    repo = ParlementairAbonnementRepository(db)
    abonnementen = await repo.list_for_scope(SCOPE_INITIATIEF, initiatief_id)
    huidige = [a.term for a in abonnementen if a.actief]
    if not huidige:
        raise HTTPException(
            status_code=400,
            detail="Voeg eerst een zoekterm toe; suggesties bouwen daarop voort.",
        )

    # PUBLIC: dit gaat over kamerstukken, en die zijn openbaar. De prompt
    # krijgt de naam van het initiatief en de zoektermen mee — beide
    # publiek — plus de beschrijving, die op de publieke initiatief-pagina
    # kan staan.
    #
    # Een eerdere versie zette dit op INTERNAL. Dat maakte de functie
    # onbruikbaar voor wie op een Claude-abonnement draait: alleen VLAM
    # declareert INTERNAL, dus de route gaf een 503 en het scherm meldde
    # "geen aanvullende zoektermen gevonden".
    llm_service = await get_llm_service(db)
    if llm_service is None:
        raise HTTPException(
            status_code=503, detail="Er is geen taalmodel geconfigureerd."
        )

    async with TkconvClient() as client:
        suggesties = await stel_voor(
            huidige_termen=huidige,
            llm_service=llm_service,
            client=client,
            # De beschrijving is tiptap-JSON; de prompt wil platte tekst.
            onderwerp=_onderwerp_van(initiatief),
        )

    return [
        SuggestieResponse(
            term=s.term,
            reden=s.reden,
            soort=s.soort,
            treffers=s.treffers,
            nieuwe_treffers=s.nieuwe_treffers,
            voorbeelden=s.voorbeelden or [],
        )
        for s in suggesties
    ]


@router.patch(
    "/{initiatief_id}/abonnementen/{abonnement_id}",
    response_model=AbonnementMetTellingResponse,
)
async def update_abonnement(
    initiatief_id: UUID,
    abonnement_id: UUID,
    payload: AbonnementUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalUser = None,
    ctx: InitiatiefContext = Depends(get_initiatief_context),
) -> AbonnementMetTellingResponse:
    """Zet een term aan of uit, of pas de notitie aan."""
    await _require_initiatief_toegang(db, ctx, initiatief_id)

    repo = ParlementairAbonnementRepository(db)
    abonnement = await repo.get(abonnement_id)
    if not _hoort_bij(abonnement, initiatief_id):
        raise HTTPException(status_code=404, detail="Abonnement niet gevonden")

    if payload.actief is not None:
        abonnement.actief = payload.actief
    if payload.notitie is not None:
        abonnement.notitie = payload.notitie
    if payload.minimum_relevantie is not None:
        abonnement.minimum_relevantie = payload.minimum_relevantie
    if payload.uitgezette_categorieen is not None:
        # Onbekende categorieën weigeren we niet: de TK-API kan er nieuwe
        # bij krijgen, en een filter dat stil een onbekende waarde slikt is
        # beter dan een 422 op iets dat morgen wel bestaat.
        abonnement.uitgezette_categorieen = payload.uitgezette_categorieen or None
    await db.commit()
    await db.refresh(abonnement)

    tellingen = await repo.telling_per_abonnement(SCOPE_INITIATIEF, initiatief_id)
    return _met_telling(abonnement, tellingen)


@router.delete("/{initiatief_id}/abonnementen/{abonnement_id}", status_code=204)
async def delete_abonnement(
    initiatief_id: UUID,
    abonnement_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: OptionalUser = None,
    ctx: InitiatiefContext = Depends(get_initiatief_context),
    actor_id: UUID | None = None,
) -> None:
    """Stop met volgen. De treffers verdwijnen mee (cascade)."""
    await _require_initiatief_toegang(db, ctx, initiatief_id)

    repo = ParlementairAbonnementRepository(db)
    abonnement = await repo.get(abonnement_id)
    if not _hoort_bij(abonnement, initiatief_id):
        raise HTTPException(status_code=404, detail="Abonnement niet gevonden")

    term = abonnement.term
    await repo.delete(abonnement)
    await log_activity(
        db,
        current_user,
        actor_id,
        "parlementair.abonnement_verwijderd",
        details={"initiatief_id": str(initiatief_id), "term": term},
    )
    await db.commit()
