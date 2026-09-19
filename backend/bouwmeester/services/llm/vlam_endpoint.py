"""Bepaal het VLAM-basisadres uit platform- of handmatige configuratie.

Er zijn twee manieren waarop Bouwmeester bij VLAM komt, en ze leveren het
adres in een andere vorm aan:

1. **De ZAD-dienst `vlam`** (productie). Het platform injecteert
   ``VLAM_API_URL`` met het adres van de interne proxy, als basisadres
   *zonder pad*: ``http://<component>.<namespace>.svc.cluster.local:8081``.
   Die proxy zet zelf de geverifieerde TLS-sessie op naar
   ``vlam-api.rijksweb.nl``, zodat wij het Rijksdienst-CA-certificaat niet
   in onze container hoeven te vertrouwen.
2. **Een handmatig adres** (``VLAM_BASE_URL``), voor lokaal werk of een
   directe endpoint. Dat is historisch mét pad ingevuld, inclusief ``/v1``.

De OpenAI-client plakt zelf ``/chat/completions`` achter de ``base_url``,
dus daar moet precies één ``/v1`` in staan. Eén te veel of te weinig geeft
een 404 die er in de logs uitziet als een storing, en dat is duur om te
herleiden. Vandaar dat dit één functie is met tests eromheen, in plaats van
een losse string-operatie in de factory.
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: Het pad-segment dat de OpenAI-compatibele API verwacht. De client voegt
#: hier zelf ``/chat/completions`` of ``/models`` aan toe.
_OPENAI_PATH_SUFFIX = "v1"


def normalize_vlam_base_url(raw: str) -> str:
    """Maak van ``raw`` een ``base_url`` die de OpenAI-client aankan.

    Zorgt dat het adres op precies één ``/v1`` eindigt, ongeacht of de bron
    het pad al meegaf. Lege of onbruikbare invoer geeft een lege string
    terug, zodat de caller dat als "niet geconfigureerd" kan behandelen.

    >>> normalize_vlam_base_url("http://proxy.svc.cluster.local:8081")
    'http://proxy.svc.cluster.local:8081/v1'
    >>> normalize_vlam_base_url("https://vlam-api.rijksweb.nl/v1/")
    'https://vlam-api.rijksweb.nl/v1'
    """
    url = (raw or "").strip()
    if not url:
        return ""

    # Zonder scheme weet urlsplit geen host te vinden en belandt alles in
    # het pad; dan is het geen bruikbaar adres.
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return ""

    path = parts.path.rstrip("/")
    segments = [s for s in path.split("/") if s]
    if not segments or segments[-1] != _OPENAI_PATH_SUFFIX:
        segments.append(_OPENAI_PATH_SUFFIX)

    rebuilt_path = "/" + "/".join(segments)
    return f"{parts.scheme}://{parts.netloc}{rebuilt_path}"


def resolve_vlam_base_url(platform_url: str, manual_url: str) -> str:
    """Kies tussen het platform-adres en een handmatig adres.

    Het platform-adres wint: de ZAD-dienst leidt het af uit de
    clusterconfiguratie en houdt het in de pas met de netwerkregel die het
    verkeer toestaat. Een handmatige waarde kan blijven staan nadat de
    endpoint verhuisd is — precies wat er gebeurde toen de demo-omgeving
    verdween en de ingestelde URL naar een dode host bleef wijzen.
    """
    return normalize_vlam_base_url(platform_url) or normalize_vlam_base_url(manual_url)
