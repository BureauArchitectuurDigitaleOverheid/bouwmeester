"""Een lege respons van het model krijgt een eigen fout.

Het geval, 25 september 2026. In de productielogs stond dit, vier frames
diep in de standaardbibliotheek:

    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
      File "/usr/local/lib/python3.13/json/decoder.py", line 363

Dat leest als kapotte JSON en wijst naar de parser. Wat er werkelijk aan
de hand was: de provider gaf een lege string terug. Dat verschil kostte
een middag zoeken, en het staat nergens in die traceback.
"""

import pytest

from bouwmeester.services.llm.base import BaseLLMService, LegeLLMResponsError


class _Svc(BaseLLMService):
    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        return ""


def _parse(inhoud: str) -> dict:
    return _Svc.__new__(_Svc)._parse_json(inhoud)


class TestLegeRespons:
    def test_lege_string(self):
        with pytest.raises(LegeLLMResponsError):
            _parse("")

    def test_alleen_witruimte(self):
        """Een antwoord van louter newlines is net zo onbruikbaar."""
        with pytest.raises(LegeLLMResponsError):
            _parse("  \n\n  ")

    def test_de_melding_noemt_de_oorzaak(self):
        """Niet "Expecting value", maar wat er werkelijk misging."""
        with pytest.raises(LegeLLMResponsError, match="lege respons"):
            _parse("")

    def test_blijft_een_valueerror(self):
        """Bestaande `except Exception`-paden moeten hem blijven vangen.

        Een lege respons hoort zacht te falen: het stuk wordt dan zonder
        samenvatting gepost, niet helemaal niet.
        """
        with pytest.raises(ValueError):
            _parse("")


class TestGeldigeInvoerBlijftWerken:
    def test_gewone_json(self):
        assert _parse('{"a": 1}') == {"a": 1}

    def test_json_in_een_codeblok(self):
        assert _parse('```json\n{"a": 1}\n```') == {"a": 1}

    def test_trailing_comma(self):
        assert _parse('{"a": 1,}') == {"a": 1}

    def test_echte_kapotte_json_blijft_jsondecodeerror(self):
        """Hier is de oorspronkelijke melding wél de juiste."""
        import json

        with pytest.raises(json.JSONDecodeError):
            _parse("{dit is geen json")
