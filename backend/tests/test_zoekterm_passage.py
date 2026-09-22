"""Tests voor het knippen rond de vindplaats van een zoekterm.

Het geval dat dit nodig maakte, gemeten op 22 september 2026: de memorie
van toelichting bij de EZ-begroting (2026D38772) is 409.827 tekens en
noemt "Nederlandse Digitale Dienst" op positie 44.954 en 262.182. De
extractie kapte op 15.000, dus het model kreeg alleen de voorpagina met
begrotingsstaten en gaf een relevantiescore van 8 aan een stuk dat
beschrijft wat de dienst gaat doen. Na deze fix: 78.
"""

from bouwmeester.services.zoekterm_passage import (
    KNIP_VANAF,
    MAX_TOTAAL,
    knip_rond_termen,
)


def _lang_document(term_op: list[int], lengte: int = 400_000) -> str:
    """Een lang document met de term op de gegeven posities."""
    vulling = list("x" * lengte)
    for positie in term_op:
        zin = "de Nederlandse Digitale Dienst krijgt vorm"
        vulling[positie : positie + len(zin)] = list(zin)
    return "".join(vulling)


class TestKorteDocumenten:
    def test_kort_document_gaat_in_zijn_geheel_mee(self):
        # Bij een kort stuk is de hele tekst de context; knippen zou alleen
        # informatie weggooien.
        tekst = "Een kort kamerstuk over de Nederlandse Digitale Dienst."
        assert knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"]) == tekst

    def test_lege_tekst(self):
        assert knip_rond_termen("", ["NLDD"]) == ""

    def test_precies_op_de_grens(self):
        tekst = "a" * KNIP_VANAF
        assert knip_rond_termen(tekst, ["NLDD"]) == tekst


class TestLangeDocumenten:
    def test_vindplaats_voorbij_de_oude_afkap_komt_mee(self):
        """Het geval uit productie: de term staat op positie 44.954."""
        tekst = _lang_document([44_954])

        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])

        assert "Nederlandse Digitale Dienst" in resultaat
        # En het resultaat is klein genoeg voor een prompt.
        assert len(resultaat) <= MAX_TOTAAL

    def test_meerdere_vindplaatsen_komen_allemaal_mee(self):
        tekst = _lang_document([44_954, 262_182])
        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])
        assert resultaat.count("Nederlandse Digitale Dienst") >= 2

    def test_de_kop_gaat_mee(self):
        """Zonder de kop leest een passage uit het midden als een losse zin."""
        tekst = "BEGROTING VAN HET MINISTERIE VAN EZ" + _lang_document([50_000])
        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])
        assert "BEGROTING VAN HET MINISTERIE" in resultaat

    def test_weglating_is_zichtbaar(self):
        """Twee losse passages mogen niet als doorlopend betoog lezen."""
        tekst = _lang_document([50_000, 300_000])
        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])
        assert "[...]" in resultaat

    def test_zonder_vindplaats_valt_het_terug_op_het_begin(self):
        """Kan gebeuren als de extractie de term al had afgekapt.

        Niet ideaal, maar een lege prompt is erger: dan weet het model
        helemaal niets.
        """
        tekst = "y" * 100_000
        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])
        assert len(resultaat) == MAX_TOTAAL
        assert resultaat.startswith("y")

    def test_blijft_onder_de_bovengrens(self):
        # Twintig vindplaatsen mogen de prompt niet laten ontploffen.
        tekst = _lang_document([i * 15_000 for i in range(1, 21)])
        resultaat = knip_rond_termen(tekst, ["Nederlandse Digitale Dienst"])
        assert len(resultaat) <= MAX_TOTAAL

    def test_hoofdletterongevoelig(self):
        tekst = "z" * 50_000 + "de nederlandse digitale dienst" + "z" * 50_000
        resultaat = knip_rond_termen(tekst, ['"Nederlandse Digitale Dienst"'])
        assert "nederlandse digitale dienst" in resultaat

    def test_gequote_term_werkt(self):
        """De termen komen als zoekopdracht binnen, dus met quotes."""
        tekst = _lang_document([50_000])
        resultaat = knip_rond_termen(tekst, ['"Nederlandse Digitale Dienst"'])
        assert "Nederlandse Digitale Dienst" in resultaat

    def test_meerdere_termen(self):
        tekst = "q" * 40_000 + "de doorbraakfunctie" + "q" * 40_000
        resultaat = knip_rond_termen(
            tekst, ['"Nederlandse Digitale Dienst"', '"doorbraakfunctie"']
        )
        assert "doorbraakfunctie" in resultaat

    def test_te_korte_term_wordt_genegeerd(self):
        # Een term van twee tekens matcht overal en zou het venster
        # betekenisloos maken.
        tekst = _lang_document([50_000])
        resultaat = knip_rond_termen(tekst, ["xx"])
        assert len(resultaat) == MAX_TOTAAL
