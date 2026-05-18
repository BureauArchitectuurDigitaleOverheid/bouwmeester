"""
Fortes Change Cloud OData v4 client.

Async client for interacting with the FCC OData API. Supports metadata
discovery, entity CRUD, and automatic pagination via @odata.nextLink.

Authentication uses HTTP Basic with an empty username and the API key as
password -- this is how FCC exposes its OData endpoints.

Note on null handling: FCC omits fields that are null or empty from the
JSON response body. Callers should treat missing keys as None rather than
expecting every property to be present.
"""

import logging
from typing import Any

import httpx
from defusedxml.ElementTree import fromstring as xml_fromstring

logger = logging.getLogger(__name__)

# OData XML namespaces used in $metadata responses
_EDMX_NS = "http://docs.oasis-open.org/odata/ns/edmx"
_EDM_NS = "http://docs.oasis-open.org/odata/ns/edm"


class FccODataClient:
    """
    Async OData v4 client for Fortes Change Cloud.

    Usage::

        async with FccODataClient(base_url, api_key) as fcc:
            meta = await fcc.discover_metadata()
            projects = await fcc.fetch_entities("Projects", top=10)
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        """
        Initialise the FCC client.

        Args:
            base_url: Root URL of the OData service
                      (e.g. ``https://example.fortescloud.com/odata``).
            api_key:  API key used as the Basic-auth password.
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._http_client: httpx.AsyncClient | None = None

    # -- lifecycle -----------------------------------------------------------

    def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create the underlying httpx client."""
        if self._http_client is None:
            transport = httpx.AsyncHTTPTransport(retries=3)
            self._http_client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(30.0),
                follow_redirects=True,
                auth=httpx.BasicAuth(username="", password=self.api_key),
            )
        return self._http_client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def __aenter__(self) -> "FccODataClient":
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        await self.close()

    # -- metadata discovery --------------------------------------------------

    async def discover_metadata(self) -> dict[str, dict[str, list[str]]]:
        """Fetch the ``$metadata`` document and extract entity types.

        Returns:
            A dict of the form::

                {
                    "entity_sets": {
                        "Projects": ["Id", "Name", "Budget", ...],
                        "Tasks": ["Id", "Title", "Status", ...],
                    }
                }
        """
        client = self._get_http_client()
        url = f"{self.base_url}/$metadata"

        logger.info("Fetching FCC OData metadata from %s", url)

        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error fetching metadata: %s %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise
        except httpx.RequestError as exc:
            logger.error("Request error fetching metadata: %s", exc)
            raise

        return self._parse_metadata_xml(response.text)

    @staticmethod
    def _parse_metadata_xml(xml_text: str) -> dict[str, dict[str, list[str]]]:
        """Parse an OData $metadata XML document into a simplified dict."""
        # $metadata is fetched over HTTP from the external FCC endpoint; the
        # defusedxml parser rejects entity-expansion / XXE that stdlib
        # ElementTree allows.
        root = xml_fromstring(xml_text)

        # Collect EntityType definitions: name -> [property names]
        entity_types: dict[str, list[str]] = {}
        for entity_type in root.iter(f"{{{_EDM_NS}}}EntityType"):
            type_name = entity_type.attrib.get("Name", "")
            props = [
                prop.attrib["Name"]
                for prop in entity_type.iter(f"{{{_EDM_NS}}}Property")
                if "Name" in prop.attrib
            ]
            if type_name:
                entity_types[type_name] = props

        # Map EntitySet names to their EntityType properties
        entity_sets: dict[str, list[str]] = {}
        for entity_set in root.iter(f"{{{_EDM_NS}}}EntitySet"):
            set_name = entity_set.attrib.get("Name", "")
            # EntityType attribute looks like "Namespace.TypeName"
            type_ref = entity_set.attrib.get("EntityType", "")
            type_name = type_ref.rsplit(".", 1)[-1] if type_ref else ""
            if set_name and type_name in entity_types:
                entity_sets[set_name] = entity_types[type_name]
            elif set_name:
                entity_sets[set_name] = []

        logger.info(
            "Discovered %d entity sets with %d entity types",
            len(entity_sets),
            len(entity_types),
        )

        return {"entity_sets": entity_sets}

    # -- entity CRUD ---------------------------------------------------------

    async def fetch_entities(
        self,
        entity_name: str,
        *,
        filters: str | None = None,
        select: list[str] | None = None,
        expand: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch entities with OData query options, following ``@odata.nextLink``.

        Args:
            entity_name: The entity set name (e.g. ``"Projects"``).
            filters: An OData ``$filter`` expression.
            select: List of property names for ``$select``.
            expand: An OData ``$expand`` expression.
            top: Maximum number of records to return per page (``$top``).
            skip: Number of records to skip (``$skip``).
            orderby: An OData ``$orderby`` expression.

        Returns:
            Flat list of entity dicts collected across all pages.
        """
        client = self._get_http_client()

        params: dict[str, str] = {}
        if filters:
            params["$filter"] = filters
        if select:
            params["$select"] = ",".join(select)
        if expand:
            params["$expand"] = expand
        if top is not None:
            params["$top"] = str(top)
        if skip is not None:
            params["$skip"] = str(skip)
        if orderby:
            params["$orderby"] = orderby

        url: str | None = f"{self.base_url}/{entity_name}"
        all_results: list[dict[str, Any]] = []
        max_pages = 100  # Guard against infinite pagination loops

        logger.info(
            "Fetching FCC entities '%s' (filter=%s, top=%s, skip=%s)",
            entity_name,
            filters,
            top,
            skip,
        )

        try:
            page = 0
            while url is not None:
                page += 1
                if page > max_pages:
                    logger.warning(
                        "Pagination limit (%d pages) reached for '%s', "
                        "stopping with %d results",
                        max_pages,
                        entity_name,
                        len(all_results),
                    )
                    break

                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                all_results.extend(data.get("value", []))

                # Follow @odata.nextLink for server-driven paging.
                # After the first request the next-link URL is absolute
                # and already contains query parameters.
                url = data.get("@odata.nextLink")
                params = {}

            logger.info(
                "Fetched %d '%s' entities in total", len(all_results), entity_name
            )
            return all_results

        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error fetching '%s': %s %s",
                entity_name,
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise
        except httpx.RequestError as exc:
            logger.error("Request error fetching '%s': %s", entity_name, exc)
            raise

    async def get_entity(
        self,
        entity_name: str,
        key: str,
        key_field: str = "Portfolio_itemKey",
    ) -> dict[str, Any] | None:
        """Fetch a single entity by its key using ``$filter``.

        FCC OData does not support key-based lookup (``/Entity(key)``),
        so we use ``$filter={key_field} eq '{key}'`` instead.

        Args:
            entity_name: The entity set name (e.g. ``"Portfolio_item"``).
            key: The entity key value (e.g. ``"234196"``).
            key_field: The property name used as primary key.

        Returns:
            The entity dict, or ``None`` if not found.
        """
        results = await self.fetch_entities(
            entity_name,
            filters=f"{key_field} eq '{key}'",
            top=1,
        )
        if results:
            return results[0]
        logger.debug("Entity '%s' with %s='%s' not found", entity_name, key_field, key)
        return None

    async def create_entity(
        self, entity_name: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new entity via POST.

        Args:
            entity_name: The entity set name.
            data: The entity payload.

        Returns:
            The created entity as returned by the server.
        """
        client = self._get_http_client()
        url = f"{self.base_url}/{entity_name}"

        logger.info("Creating FCC entity in '%s'", entity_name)

        try:
            response = await client.post(url, json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error creating '%s': %s %s",
                entity_name,
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise
        except httpx.RequestError as exc:
            logger.error("Request error creating '%s': %s", entity_name, exc)
            raise

    async def update_entity(
        self, entity_name: str, key: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing entity via PATCH.

        Tries ``PATCH /{entity}('{key}')`` first.  If the server returns
        400 (FCC doesn't support key-based URLs), falls back to PATCH via
        ``$filter`` to locate the entity first.

        Returns:
            The updated entity, or the input data merged with the key.
        """
        client = self._get_http_client()

        # Try standard OData PATCH first
        url = f"{self.base_url}/{entity_name}('{key}')"
        logger.info("Updating FCC entity '%s(%s)'", entity_name, key)

        try:
            response = await client.patch(url, json=data)
            if response.status_code == 400:
                # FCC doesn't support key-based PATCH — log and raise
                # rather than silently creating a duplicate via POST
                logger.warning(
                    "PATCH returned 400 for '%s(%s)': %s",
                    entity_name,
                    key,
                    response.text[:500],
                )
                response.raise_for_status()
            response.raise_for_status()

            if response.status_code == 204:
                return {**data, "Portfolio_itemKey": key}

            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HTTP error updating '%s(%s)': %s %s",
                entity_name,
                key,
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise
        except httpx.RequestError as exc:
            logger.error("Request error updating '%s(%s)': %s", entity_name, key, exc)
            raise
