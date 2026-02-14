"""
Tweede Kamer and Eerste Kamer API clients for parliamentary data.

Integrates with the official OData APIs to retrieve parliamentary items
(moties, kamervragen, toezeggingen, etc.) from both chambers of Dutch
parliament.
"""

import logging
from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _odata_escape(value: str) -> str:
    """Escape a string value for use in OData filter expressions."""
    return value.replace("'", "''")


class MotieData(BaseModel):
    """Structured data for a motie from either parliamentary chamber."""

    zaak_id: str
    zaak_nummer: str
    titel: str
    onderwerp: str
    datum: datetime | None = None
    indieners: list[str] = []
    document_tekst: str | None = None
    document_url: str | None = None
    kabinetsappreciatie: str | None = None
    bron: str  # "tweede_kamer" or "eerste_kamer"


class ZaakData(BaseModel):
    """Structured data for a generic Zaak (parliamentary case)."""

    zaak_id: str
    zaak_nummer: str
    titel: str
    onderwerp: str
    soort: str
    datum: datetime | None = None
    indieners: list[str] = []
    document_tekst: str | None = None
    document_url: str | None = None
    termijn: datetime | None = None
    bron: str = "tweede_kamer"


class ToezeggingData(BaseModel):
    """Structured data for a toezegging (government commitment)."""

    toezegging_id: str
    nummer: str
    tekst: str
    naam_bewindspersoon: str | None = None
    ministerie: str | None = None
    status: str | None = None
    datum_nakoming: datetime | None = None
    activiteit_nummer: str | None = None
    bron: str = "tweede_kamer"


class TweedeKamerClient:
    """
    Client for Tweede Kamer Open Data API.

    Fetches moties and related metadata from the parliamentary data magazine.
    """

    def __init__(
        self,
        base_url: str = "https://gegevensmagazijn.tweedekamer.nl/OData/v4/2.0",
        session: AsyncSession | None = None,
    ):
        """
        Initialize TK API client.

        Args:
            base_url: OData API base URL
            session: Optional SQLAlchemy session (for future DB integration)
        """
        self.base_url = base_url.rstrip("/")
        self.session = session
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create httpx client with retry and timeout configuration."""
        if self._http_client is None:
            transport = httpx.AsyncHTTPTransport(retries=3)
            self._http_client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "TweedeKamerClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.close()

    async def fetch_moties(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[MotieData]:
        """Fetch adopted moties from Tweede Kamer API.

        Delegates to fetch_zaak_by_soort with 'aangenomen' besluit filter,
        then converts ZaakData to MotieData for backward compatibility.
        """
        zaken = await self.fetch_zaak_by_soort(
            soort="Motie",
            since=since,
            limit=limit,
            besluit_filter="contains(BesluitSoort,'aangenomen')",
        )
        return [
            MotieData(
                zaak_id=z.zaak_id,
                zaak_nummer=z.zaak_nummer,
                titel=z.titel,
                onderwerp=z.onderwerp,
                datum=z.datum,
                indieners=z.indieners,
                document_tekst=z.document_tekst,
                document_url=z.document_url,
                kabinetsappreciatie=None,
                bron=z.bron,
            )
            for z in zaken
        ]

    async def fetch_zaak_by_soort(
        self,
        soort: str,
        since: datetime | None = None,
        limit: int = 100,
        besluit_filter: str | None = None,
    ) -> list[ZaakData]:
        """Fetch Zaak records of a given Soort (type).

        Args:
            soort: Zaak type to query (e.g. 'Schriftelijke vragen')
            since: Optional datetime to filter by GewijzigdOp
            limit: Maximum number of results
            besluit_filter: Optional Besluit filter
                (e.g. "contains(BesluitSoort,'aangenomen')")
        """
        client = self._get_http_client()

        escaped_soort = _odata_escape(soort)

        if besluit_filter:
            # Query via Besluit, expanding Zaak (like fetch_moties)
            filters = [
                besluit_filter,
                f"Zaak/any(z:z/Soort eq '{escaped_soort}')",
            ]
            if since:
                since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
                filters.append(f"GewijzigdOp gt {since_str}")

            params = {
                "$filter": " and ".join(filters),
                "$orderby": "GewijzigdOp desc",
                "$top": str(limit),
                "$expand": "Zaak($select=Id,Nummer,Titel,Onderwerp,GestartOp)",
            }
            url = f"{self.base_url}/Besluit"
        else:
            # Query Zaak directly
            filters = [f"Soort eq '{escaped_soort}'"]
            if since:
                since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
                filters.append(f"GewijzigdOp gt {since_str}")

            params = {
                "$filter": " and ".join(filters),
                "$orderby": "GewijzigdOp desc",
                "$top": str(limit),
                "$select": "Id,Nummer,Titel,Onderwerp,GestartOp,Termijn",
            }
            url = f"{self.base_url}/Zaak"

        logger.info(
            f"Fetching Zaak soort='{soort}' from TK API (since={since}, limit={limit})"
        )

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results: list[ZaakData] = []
            seen_zaak_ids: set[str] = set()

            if besluit_filter:
                # Besluit-based: extract Zaak from expansion
                for besluit in data.get("value", []):
                    for zaak in besluit.get("Zaak", []):
                        zaak_id = zaak.get("Id")
                        if not zaak_id or zaak_id in seen_zaak_ids:
                            continue
                        seen_zaak_ids.add(zaak_id)
                        results.append(await self._zaak_to_data(zaak, soort))
            else:
                # Direct Zaak query
                for zaak in data.get("value", []):
                    zaak_id = zaak.get("Id")
                    if not zaak_id or zaak_id in seen_zaak_ids:
                        continue
                    seen_zaak_ids.add(zaak_id)
                    results.append(await self._zaak_to_data(zaak, soort))

            logger.info(f"Fetched {len(results)} Zaak records (soort='{soort}')")
            return results

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching Zaak soort='{soort}': "
                f"{e.response.status_code} {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching Zaak soort='{soort}': {e}")
            raise

    async def _zaak_to_data(self, zaak: dict[str, Any], soort: str) -> ZaakData:
        """Convert a raw Zaak dict to ZaakData with enrichment."""
        zaak_id = zaak["Id"]
        zaak_nummer = zaak.get("Nummer") or ""

        indieners = await self._fetch_indieners(zaak_id)
        document_tekst, document_url = await self._fetch_document_text(
            zaak_id, zaak_nummer
        )

        datum = None
        if zaak.get("GestartOp"):
            try:
                parsed = datetime.fromisoformat(
                    zaak["GestartOp"].replace("Z", "+00:00")
                )
                if parsed.year > 1:
                    datum = parsed
            except (ValueError, AttributeError):
                pass

        termijn = None
        if zaak.get("Termijn"):
            try:
                parsed = datetime.fromisoformat(zaak["Termijn"].replace("Z", "+00:00"))
                if parsed.year > 1:
                    termijn = parsed
            except (ValueError, AttributeError):
                pass

        return ZaakData(
            zaak_id=zaak_id,
            zaak_nummer=zaak_nummer,
            titel=zaak.get("Titel") or "",
            onderwerp=zaak.get("Onderwerp") or "",
            soort=soort,
            datum=datum,
            indieners=indieners,
            document_tekst=document_tekst,
            document_url=document_url,
            termijn=termijn,
            bron="tweede_kamer",
        )

    async def fetch_toezeggingen(
        self,
        ministerie: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[ToezeggingData]:
        """Fetch toezeggingen (government commitments) from TK API.

        Args:
            ministerie: Filter by ministry (e.g. 'Binnenlandse Zaken')
            since: Optional datetime to filter by GewijzigdOp
            limit: Maximum number of results
        """
        client = self._get_http_client()

        filters = ["Verwijderd eq false"]
        if ministerie:
            filters.append(f"contains(Ministerie,'{_odata_escape(ministerie)}')")
        if since:
            since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append(f"GewijzigdOp gt {since_str}")

        params = {
            "$filter": " and ".join(filters),
            "$orderby": "GewijzigdOp desc",
            "$top": str(limit),
            "$select": (
                "Id,Nummer,Tekst,Naam,Achternaam,Initialen,"
                "Ministerie,Status,DatumNakoming,ActiviteitNummer"
            ),
        }

        url = f"{self.base_url}/Toezegging"

        logger.info(
            f"Fetching toezeggingen from TK API "
            f"(ministerie={ministerie}, since={since}, limit={limit})"
        )

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            results: list[ToezeggingData] = []
            for item in data.get("value", []):
                toezegging_id = item.get("Id")
                if not toezegging_id:
                    continue

                datum_nakoming = None
                if item.get("DatumNakoming"):
                    try:
                        parsed = datetime.fromisoformat(
                            item["DatumNakoming"].replace("Z", "+00:00")
                        )
                        # TK API uses 0001-01-01 as sentinel for missing dates
                        if parsed.year > 1:
                            datum_nakoming = parsed
                    except (ValueError, AttributeError):
                        pass

                # Build bewindspersoon name
                naam_parts = [
                    item.get("Initialen", ""),
                    item.get("Achternaam", ""),
                ]
                naam = " ".join(p for p in naam_parts if p).strip()
                if not naam:
                    naam = item.get("Naam")

                results.append(
                    ToezeggingData(
                        toezegging_id=str(toezegging_id),
                        nummer=item.get("Nummer") or str(toezegging_id),
                        tekst=item.get("Tekst", ""),
                        naam_bewindspersoon=naam,
                        ministerie=item.get("Ministerie"),
                        status=item.get("Status"),
                        datum_nakoming=datum_nakoming,
                        activiteit_nummer=item.get("ActiviteitNummer"),
                        bron="tweede_kamer",
                    )
                )

            logger.info(f"Fetched {len(results)} toezeggingen")
            return results

        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error fetching toezeggingen: "
                f"{e.response.status_code} {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error fetching toezeggingen: {e}")
            raise

    async def _fetch_document_text(
        self, zaak_id: str, zaak_nummer: str
    ) -> tuple[str | None, str | None]:
        """
        Fetch document text and URL for a zaak.

        Args:
            zaak_id: The Zaak identifier (UUID)
            zaak_nummer: The Zaak number (e.g. "2026Z01937")

        Returns:
            Tuple of (document_text, document_url). Either may be None.
        """
        client = self._get_http_client()

        params = {
            "$filter": f"Zaak/any(z:z/Id eq {zaak_id})",
            "$select": "Id,Onderwerp,Titel,ContentType,DocumentNummer",
            "$top": "1",
        }

        url = f"{self.base_url}/Document"

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            documents = data.get("value", [])

            if not documents:
                logger.debug(f"No document found for zaak {zaak_id}")
                return None, None

            doc = documents[0]
            doc_id = doc.get("Id")
            doc_nummer = doc.get("DocumentNummer")

            # Try to fetch the full HTML content of the document
            full_text = await self._fetch_document_html(doc_id) if doc_id else None
            if not full_text:
                full_text = doc.get("Onderwerp") or doc.get("Titel")

            # Construct URL to the document on tweedekamer.nl
            doc_url = None
            if zaak_nummer and doc_nummer:
                doc_url = (
                    f"https://www.tweedekamer.nl/kamerstukken/"
                    f"detail?id={zaak_nummer}&did={doc_nummer}"
                )

            return full_text, doc_url

        except httpx.HTTPStatusError as e:
            logger.warning(
                f"HTTP error fetching document for zaak {zaak_id}: "
                f"{e.response.status_code}"
            )
            return None, None
        except Exception as e:
            logger.warning(f"Error fetching document for zaak {zaak_id}: {e}")
            return None, None

    async def _fetch_document_html(self, doc_id: str) -> str | None:
        """
        Fetch the HTML content of a document and extract plain text.

        Args:
            doc_id: The Document identifier

        Returns:
            Plain text extracted from HTML, or None if unavailable.
        """
        client = self._get_http_client()

        url = f"{self.base_url}/Document({doc_id})/resource"

        try:
            response = await client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "html" in content_type or "xml" in content_type:
                import re

                text = response.text
                # Reject binary content that was misidentified as text
                if "\x00" in text:
                    logger.debug(f"Document {doc_id} contains null bytes, skipping")
                    return None
                # Strip HTML tags to get plain text
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()
                # Limit length to avoid storing huge texts
                if len(text) > 5000:
                    text = text[:5000] + "..."
                return text if text else None

            return None

        except Exception as e:
            logger.debug(f"Could not fetch document HTML for {doc_id}: {e}")
            return None

    async def _fetch_indieners(self, zaak_id: str) -> list[str]:
        """
        Fetch indieners (submitters) for a zaak.

        Args:
            zaak_id: The Zaak identifier

        Returns:
            List of indiener names
        """
        client = self._get_http_client()

        # Query ZaakActor entities related to this Zaak
        params = {
            "$filter": f"Zaak_Id eq {zaak_id}",
            "$select": "ActorNaam,ActorFractie",
        }

        url = f"{self.base_url}/ZaakActor"

        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            actors = data.get("value", [])

            # Chamber-level actors (e.g. "TK", "EK") are not real indieners
            _skip_fracties = {"TK", "EK"}

            indieners = []
            for actor in actors:
                naam = actor.get("ActorNaam")
                if naam:
                    indieners.append(naam)
                elif (
                    fractie := actor.get("ActorFractie")
                ) and fractie not in _skip_fracties:
                    indieners.append(fractie)

            return indieners

        except httpx.HTTPStatusError as e:
            logger.warning(
                "HTTP error fetching indieners for zaak"
                f" {zaak_id}: {e.response.status_code}"
            )
            return []
        except Exception as e:
            logger.warning(f"Error fetching indieners for zaak {zaak_id}: {e}")
            return []


class EersteKamerClient:
    """
    Client for Eerste Kamer Open Data API.

    Fetches moties and related metadata from the first chamber.
    """

    def __init__(
        self,
        base_url: str = "https://gegevens.eerstekamer.nl/opendata",
        session: AsyncSession | None = None,
    ):
        """
        Initialize EK API client.

        Args:
            base_url: API base URL
            session: Optional SQLAlchemy session (for future DB integration)
        """
        self.base_url = base_url.rstrip("/")
        self.session = session
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create httpx client with retry and timeout configuration."""
        if self._http_client is None:
            transport = httpx.AsyncHTTPTransport(retries=3)
            self._http_client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "EersteKamerClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.close()

    async def fetch_moties(
        self, since: datetime | None = None, limit: int = 100
    ) -> list[MotieData]:
        """
        Fetch moties from Eerste Kamer API.

        TODO: Implement full EK API integration once API details are available.
        Current implementation is a stub that returns empty list.

        Args:
            since: Optional datetime to fetch only moties modified after this date
            limit: Maximum number of results to fetch (default 100)

        Returns:
            List of MotieData objects for adopted moties (currently empty)
        """
        logger.warning(
            "EK API not yet fully implemented - returning empty list. "
            f"Called with since={since}, limit={limit}"
        )

        # TODO: Implement full API integration:
        # 1. Query EK API for moties with appropriate filters
        # 2. Check adoption status (besluit/stemming)
        # 3. Fetch document text and indieners
        # 4. Map to MotieData with bron="eerste_kamer"
        # 5. Add proper error handling and logging

        return []

    # TODO: Implement supporting methods similar to TweedeKamerClient:
    # - async def _is_aangenomen(self, zaak_id: str) -> bool
    # - async def _fetch_document_text(self, zaak_id: str) -> str | None
    # - async def _fetch_indieners(self, zaak_id: str) -> list[str]
