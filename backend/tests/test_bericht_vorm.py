"""Hoe een bericht eruitziet in Mattermost.

Drie dingen stonden er op 24 september 2026 verkeerd in, alle drie
zichtbaar in één post:

    :question: Inbreng verslag van een schriftelijk overleg over
    cloudbeleid \\(O.a. Kamerstuk 26643-1542\\)

De emoji-code bleef letterlijk staan, de escape-backslashes werden
getoond, en in het bijbehorende inhaalbericht stond "1 stukken" met een
titel die midden in een woord afbrak ("(O.a. Ka").

De oorzaak van de eerste twee is dezelfde: het `title`-veld van een
attachment rendert geen markdown en geen `:emoji:`-codes, terwijl `text`
dat wel doet.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

from bouwmeester.services.kamerstuk_soort import CAT_VRAAG, CATEGORIE_PRESENTATIE
from bouwmeester.services.parlementair_alert_service import (
    ParlementairAlertService,
    _kort,
)

TITEL = (
    "Inbreng verslag van een schriftelijk overleg over cloudbeleid "
    "(O.a. Kamerstuk 26643-1542)"
)


def _svc() -> ParlementairAlertService:
    return ParlementairAlertService.__new__(ParlementairAlertService)


def _item(**extra) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        titel=extra.pop("titel", TITEL),
        onderwerp="Verslag van een schriftelijk overleg",
        zaak_nummer="2026D45836",
        llm_samenvatting="Meerdere fracties stellen vragen.",
        document_url="https://berthub.eu/tkconv/document.html?nummer=2026D45836",
        datum=extra.pop("datum", date(2026, 9, 24)),
        extra_data=extra,
    )


class TestTitelVanEenAlert:
    def _titel(self, **extra) -> str:
        _, props = _svc().format_alert(
            _item(categorie=CAT_VRAAG, relevantie_score=80, **extra),
            ['"cloudbeleid"'],
        )
        return props["attachments"][0]["title"]

    def test_geen_emoji_code(self):
        """`:question:` bleef letterlijk staan in het title-veld."""
        assert ":question:" not in self._titel()

    def test_wel_een_icoon(self):
        assert self._titel().startswith(CATEGORIE_PRESENTATIE[CAT_VRAAG]["teken"])

    def test_geen_escape_backslashes(self):
        """De haakjes in een kamerstuknummer werden getoond als \\( en \\)."""
        titel = self._titel()
        assert "\\(" not in titel
        assert "\\)" not in titel
        assert "(O.a. Kamerstuk 26643-1542)" in titel

    def test_de_hele_titel_staat_erin(self):
        assert "schriftelijk overleg over cloudbeleid" in self._titel()

    def test_fallback_is_ook_plat(self):
        """Dit is wat een telefoonnotificatie toont."""
        _, props = _svc().format_alert(
            _item(categorie=CAT_VRAAG, relevantie_score=80), ['"cloudbeleid"']
        )
        assert "\\(" not in props["attachments"][0]["fallback"]


class TestElkeCategorieHeeftEenTeken:
    def test_geen_enkele_categorie_mist_er_een(self):
        """Anders valt het icoon stil weg in plaats van verkeerd te staan."""
        for categorie, presentatie in CATEGORIE_PRESENTATIE.items():
            assert presentatie.get("teken"), categorie

    def test_het_teken_is_geen_emoji_code(self):
        for categorie, presentatie in CATEGORIE_PRESENTATIE.items():
            assert not presentatie["teken"].startswith(":"), categorie


class TestInhaalbericht:
    def _props(self, aantal: int) -> dict:
        items = [
            _item(titel=f"{TITEL} deel {i}", categorie=CAT_VRAAG) for i in range(aantal)
        ]
        _, props = _svc().format_inhaalslag(
            [SimpleNamespace(id=uuid4(), term="rijkscloud")], items
        )
        return props["attachments"][0]

    def test_enkelvoud_bij_een_stuk(self):
        """Er stond "1 stukken uit de afgelopen week gevonden"."""
        assert self._props(1)["title"] == "1 stuk uit de afgelopen week gevonden"

    def test_meervoud_bij_meer(self):
        assert self._props(3)["title"].startswith("3 stukken")

    def test_titel_breekt_niet_midden_in_een_woord(self):
        tekst = self._props(1)["text"]
        assert "(O.a. Ka " not in tekst
        assert "…" in tekst


class TestKort:
    def test_korte_titel_blijft_heel(self):
        assert _kort("Een korte titel", 70) == "Een korte titel"

    def test_lange_titel_krijgt_een_beletselteken(self):
        uit = _kort(TITEL, 70)
        assert uit.endswith("…")
        assert len(uit) <= 71

    def test_breekt_op_een_woordgrens(self):
        uit = _kort("woord " * 30, 70)
        assert "…" in uit
        # Geen half woord voor het beletselteken.
        assert uit.rstrip("…").endswith("woord")

    def test_geen_losse_leestekens_voor_het_teken(self):
        assert not _kort("Een titel met een komma, en meer tekst " * 3, 40).endswith(
            ",…"
        )

    def test_een_lang_woord_wordt_gewoon_afgekapt(self):
        """Teruggaan naar de spatie zou hier de halve titel weggooien."""
        uit = _kort("x" * 100, 70)
        assert len(uit) == 71
