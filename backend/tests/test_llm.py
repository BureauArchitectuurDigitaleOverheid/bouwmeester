"""Tests for the LLM multi-provider architecture, admin config, and API endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    EdgeRelevanceResult,
    ProviderCapabilities,
    SummarizeResult,
    TagExtractionResult,
    TagSuggestionResult,
)
from bouwmeester.services.llm.factory import (
    _ensure_services,
    _load_config,
    clear_config_cache,
)
from bouwmeester.services.llm.prompts import (
    MAX_DESCRIPTION_IN_PROMPT,
    MAX_TAGS_IN_PROMPT,
    MAX_TEXT_IN_PROMPT,
    build_edge_relevance_prompt,
    build_extract_tags_prompt,
    build_suggest_tags_prompt,
    build_summarize_prompt,
)

# ---------------------------------------------------------------------------
# _parse_json (via BaseLLMService)
# ---------------------------------------------------------------------------


class DummyLLMService(BaseLLMService):
    """Concrete subclass for testing base class methods."""

    capabilities = ProviderCapabilities(
        allowed_data={DataSensitivity.PUBLIC, DataSensitivity.INTERNAL}
    )

    def __init__(self, responses: list[str] | None = None):
        self._responses = responses or []
        self._call_idx = 0

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        if self._call_idx < len(self._responses):
            resp = self._responses[self._call_idx]
            self._call_idx += 1
            return resp
        return "{}"


class TestParseJson:
    def test_parse_plain_json(self):
        service = DummyLLMService()
        result = service._parse_json('{"matched_tags": ["a", "b"]}')
        assert result == {"matched_tags": ["a", "b"]}

    def test_parse_json_code_block(self):
        service = DummyLLMService()
        text = '```json\n{"score": 0.9}\n```'
        result = service._parse_json(text)
        assert result == {"score": 0.9}

    def test_parse_generic_code_block(self):
        service = DummyLLMService()
        text = '```\n{"key": "val"}\n```'
        result = service._parse_json(text)
        assert result == {"key": "val"}

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises an exception (callers handle this)."""
        service = DummyLLMService()
        with pytest.raises(Exception):
            service._parse_json("this is not json at all")


# ---------------------------------------------------------------------------
# DataSensitivity / ProviderCapabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_public_only_supports_public(self):
        caps = ProviderCapabilities(allowed_data={DataSensitivity.PUBLIC})
        assert caps.supports(DataSensitivity.PUBLIC)
        assert not caps.supports(DataSensitivity.INTERNAL)
        assert not caps.supports(DataSensitivity.CONFIDENTIAL)

    def test_all_capabilities(self):
        caps = ProviderCapabilities(
            allowed_data={
                DataSensitivity.PUBLIC,
                DataSensitivity.INTERNAL,
                DataSensitivity.CONFIDENTIAL,
            }
        )
        assert caps.supports(DataSensitivity.PUBLIC)
        assert caps.supports(DataSensitivity.INTERNAL)
        assert caps.supports(DataSensitivity.CONFIDENTIAL)


# ---------------------------------------------------------------------------
# BaseLLMService methods (via DummyLLMService)
# ---------------------------------------------------------------------------


class TestBaseLLMServiceMethods:
    @pytest.mark.asyncio
    async def test_extract_tags(self):
        resp = (
            '{"samenvatting": "test",'
            ' "matched_tags": ["a"],'
            ' "suggested_new_tags": ["b"]}'
        )
        service = DummyLLMService(responses=[resp])
        result = await service.extract_tags(
            titel="Test",
            onderwerp="Onderwerp",
            document_tekst=None,
            bestaande_tags=["a", "c"],
        )
        assert isinstance(result, TagExtractionResult)
        assert result.matched_tags == ["a"]
        assert result.suggested_new_tags == ["b"]
        assert result.samenvatting == "test"

    @pytest.mark.asyncio
    async def test_extract_tags_handles_error(self):
        service = DummyLLMService(responses=["not json"])
        result = await service.extract_tags(
            titel="Test",
            onderwerp="Onderwerp",
            document_tekst=None,
            bestaande_tags=[],
        )
        assert isinstance(result, TagExtractionResult)
        assert result.matched_tags == []

    @pytest.mark.asyncio
    async def test_suggest_tags(self):
        service = DummyLLMService(
            responses=['{"matched_tags": ["x"], "suggested_new_tags": ["y"]}']
        )
        result = await service.suggest_tags(
            title="Title", description="Desc", node_type="dossier", bestaande_tags=["x"]
        )
        assert isinstance(result, TagSuggestionResult)
        assert result.matched_tags == ["x"]
        assert result.suggested_new_tags == ["y"]

    @pytest.mark.asyncio
    async def test_score_edge_relevance(self):
        resp = (
            '{"score": 0.85,'
            ' "suggested_edge_type": "gerelateerd_aan",'
            ' "reason": "Both about housing"}'
        )
        service = DummyLLMService(responses=[resp])
        result = await service.score_edge_relevance(
            source_title="Node A",
            source_description="Desc A",
            target_title="Node B",
            target_description="Desc B",
        )
        assert isinstance(result, EdgeRelevanceResult)
        assert result.score == 0.85
        assert result.suggested_edge_type == "gerelateerd_aan"

    @pytest.mark.asyncio
    async def test_summarize(self):
        service = DummyLLMService(responses=["Een korte samenvatting."])
        result = await service.summarize(text="Heel lange tekst...")
        assert isinstance(result, SummarizeResult)
        assert result.summary == "Een korte samenvatting."


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    def test_extract_tags_prompt_contains_key_parts(self):
        prompt = build_extract_tags_prompt(
            titel="Motie over woningbouw",
            onderwerp="Woningbouw",
            document_tekst="Volledige tekst.",
            bestaande_tags=["woningbouw", "klimaat"],
            context_hint="motie",
        )
        assert "motie" in prompt.lower()
        assert "Motie over woningbouw" in prompt
        assert "woningbouw" in prompt
        assert "klimaat" in prompt

    def test_extract_tags_prompt_truncates_text(self):
        long_text = "x" * (MAX_TEXT_IN_PROMPT + 1000)
        prompt = build_extract_tags_prompt(
            titel="T", onderwerp="O", document_tekst=long_text, bestaande_tags=[]
        )
        # The long text should be truncated — prompt should not contain the full string
        assert long_text not in prompt
        # But it should contain the truncated portion
        assert "x" * MAX_TEXT_IN_PROMPT in prompt

    def test_suggest_tags_prompt_truncates_tags(self):
        many_tags = [f"tag_{i}" for i in range(MAX_TAGS_IN_PROMPT + 100)]
        prompt = build_suggest_tags_prompt(
            title="T", description="D", node_type="dossier", bestaande_tags=many_tags
        )
        # Should only include MAX_TAGS_IN_PROMPT tags
        assert f"tag_{MAX_TAGS_IN_PROMPT}" not in prompt
        assert "tag_0" in prompt

    def test_edge_relevance_prompt_truncates_descriptions(self):
        long_desc = "y" * 1000
        prompt = build_edge_relevance_prompt(
            source_title="A",
            source_description=long_desc,
            target_title="B",
            target_description=long_desc,
        )
        # Descriptions are truncated at MAX_DESCRIPTION_IN_PROMPT chars
        assert "y" * (MAX_DESCRIPTION_IN_PROMPT + 1) not in prompt

    def test_summarize_prompt_truncates_text(self):
        long_text = "z" * (MAX_TEXT_IN_PROMPT + 500)
        prompt = build_summarize_prompt(text=long_text)
        assert long_text not in prompt


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        """With a secure key, values encrypt and decrypt correctly."""
        import bouwmeester.core.encryption as enc_mod

        # Save original state
        orig_initialized = enc_mod._initialized
        orig_fernet = enc_mod._fernet

        try:
            # Force re-init
            enc_mod._initialized = False
            enc_mod._fernet = None

            with patch("bouwmeester.core.config.get_settings") as mock_settings:
                settings = mock_settings.return_value
                settings.SESSION_SECRET_KEY = "a-very-secure-test-key-1234567890"
                settings._INSECURE_SECRET_DEFAULTS = frozenset(
                    {"change-me-in-production"}
                )

                encrypted = enc_mod.encrypt_value("my-secret-key")
                assert encrypted != "my-secret-key"
                assert enc_mod.decrypt_value(encrypted) == "my-secret-key"
        finally:
            # Restore original state
            enc_mod._initialized = orig_initialized
            enc_mod._fernet = orig_fernet

    def test_decrypt_plaintext_returns_as_is(self):
        """Values stored before encryption was enabled are returned as-is."""
        import bouwmeester.core.encryption as enc_mod

        orig_initialized = enc_mod._initialized
        orig_fernet = enc_mod._fernet

        try:
            enc_mod._initialized = False
            enc_mod._fernet = None

            with patch("bouwmeester.core.config.get_settings") as mock_settings:
                settings = mock_settings.return_value
                settings.SESSION_SECRET_KEY = "secure-key-for-test"
                settings._INSECURE_SECRET_DEFAULTS = frozenset(
                    {"change-me-in-production"}
                )
                # This plaintext was never encrypted, should return as-is
                result = enc_mod.decrypt_value("plain-old-api-key")
                assert result == "plain-old-api-key"
        finally:
            enc_mod._initialized = orig_initialized
            enc_mod._fernet = orig_fernet

    def test_empty_string_passthrough(self):
        from bouwmeester.core.encryption import decrypt_value, encrypt_value

        assert encrypt_value("") == ""
        assert decrypt_value("") == ""


# ---------------------------------------------------------------------------
# Factory: _load_config and service building
# ---------------------------------------------------------------------------


class TestFactory:
    @pytest.fixture(autouse=True)
    def _reset_factory(self):
        """Reset factory caches before and after each test."""
        clear_config_cache()
        yield
        clear_config_cache()

    @pytest.fixture(autouse=True)
    def _reset_admin_defaults(self):
        """Reset the _defaults_seeded flag in admin module."""
        import bouwmeester.api.routes.admin as admin_mod

        admin_mod._defaults_seeded = False
        yield
        admin_mod._defaults_seeded = False

    @pytest.mark.asyncio
    async def test_load_config_from_db(self, db_session):
        """Config values are loaded from the app_config table."""
        from bouwmeester.models.app_config import AppConfig

        db_session.add(AppConfig(key="LLM_PROVIDER", value="vlam", is_secret=False))
        db_session.add(AppConfig(key="LLM_MODEL", value="test-model", is_secret=False))
        await db_session.flush()

        config = await _load_config(db_session)
        assert config["LLM_PROVIDER"] == "vlam"
        assert config["LLM_MODEL"] == "test-model"

    @pytest.mark.asyncio
    async def test_load_config_skips_empty_values(self, db_session):
        """Empty values are not included in the config dict."""
        from bouwmeester.models.app_config import AppConfig

        db_session.add(AppConfig(key="VLAM_API_KEY", value="", is_secret=True))
        await db_session.flush()

        config = await _load_config(db_session)
        assert "VLAM_API_KEY" not in config

    @pytest.mark.asyncio
    async def test_ensure_services_builds_claude(self, db_session):
        """With an Anthropic key, Claude service is built."""
        from bouwmeester.models.app_config import AppConfig

        db_session.add(
            AppConfig(
                key="ANTHROPIC_API_KEY",
                value="sk-test-key",
                is_secret=False,
            )
        )
        await db_session.flush()

        await _ensure_services(db_session)

        from bouwmeester.services.llm.factory import _claude_cache

        assert _claude_cache is not None

    @pytest.mark.asyncio
    async def test_clear_config_cache_resets_all(self, db_session):
        """clear_config_cache resets config and service caches."""
        from bouwmeester.models.app_config import AppConfig

        db_session.add(
            AppConfig(
                key="ANTHROPIC_API_KEY",
                value="sk-test",
                is_secret=False,
            )
        )
        await db_session.flush()
        await _ensure_services(db_session)

        from bouwmeester.services.llm import factory as fmod

        assert fmod._services_built is True
        clear_config_cache()
        assert fmod._services_built is False
        assert fmod._config_cache is None
        assert fmod._claude_cache is None


# ---------------------------------------------------------------------------
# Admin config API endpoints
# ---------------------------------------------------------------------------


class TestAdminConfigAPI:
    @pytest.fixture(autouse=True)
    def _reset_admin_defaults(self):
        """Reset the _defaults_seeded flag between tests."""
        import bouwmeester.api.routes.admin as admin_mod

        admin_mod._defaults_seeded = False
        yield
        admin_mod._defaults_seeded = False

    @pytest.mark.asyncio
    async def test_list_config_seeds_defaults(self, client):
        """GET /api/admin/config seeds default entries on first call."""
        resp = await client.get("/api/admin/config")
        assert resp.status_code == 200
        data = resp.json()
        keys = {e["key"] for e in data}
        assert "LLM_PROVIDER" in keys
        assert "ANTHROPIC_API_KEY" in keys
        assert "VLAM_API_KEY" in keys
        assert "LLM_MODEL" in keys

    @pytest.mark.asyncio
    async def test_list_config_masks_secrets(self, client):
        """Secret values are masked in the response."""
        # First seed defaults
        await client.get("/api/admin/config")
        # Set a secret value
        resp = await client.patch(
            "/api/admin/config/ANTHROPIC_API_KEY",
            json={"value": "sk-ant-api03-abcdef1234"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should be masked — original value should not be present
        assert "sk-ant-api03-abcdef1234" not in data["value"]
        assert data["value"].startswith("****")

    @pytest.mark.asyncio
    async def test_update_config_nonexistent_key(self, client):
        """PATCH with unknown key returns 404."""
        resp = await client.patch(
            "/api/admin/config/NONEXISTENT_KEY",
            json={"value": "something"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_config_stores_value(self, client):
        """PATCH stores and returns the updated value."""
        # Seed defaults
        await client.get("/api/admin/config")
        resp = await client.patch(
            "/api/admin/config/LLM_PROVIDER",
            json={"value": "vlam"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["value"] == "vlam"


# ---------------------------------------------------------------------------
# LLM API endpoints
# ---------------------------------------------------------------------------


class TestLLMEndpoints:
    @pytest.fixture(autouse=True)
    def _reset_caches(self):
        """Reset caches between tests."""
        clear_config_cache()
        yield
        clear_config_cache()

    @pytest.mark.asyncio
    async def test_suggest_tags_no_provider(self, client):
        """Without a configured LLM provider, returns available=False."""
        resp = await client.post(
            "/api/llm/suggest-tags",
            json={"title": "Test node", "node_type": "dossier"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["matched_tags"] == []

    @pytest.mark.asyncio
    async def test_suggest_edges_no_provider(self, client):
        """Without a configured LLM provider, returns available=False."""
        resp = await client.post(
            "/api/llm/suggest-edges",
            json={"node_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["suggestions"] == []

    @pytest.mark.asyncio
    async def test_summarize_no_provider(self, client):
        """Without a configured LLM provider, returns available=False."""
        resp = await client.post(
            "/api/llm/summarize",
            json={"text": "Een hele lange tekst over beleid."},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["summary"] == ""

    @pytest.mark.asyncio
    async def test_suggest_tags_with_mock_provider(self, client):
        """With a mocked LLM service, returns tag suggestions."""
        resp = '{"matched_tags": ["woningbouw"], "suggested_new_tags": ["nieuw"]}'
        mock_service = DummyLLMService(responses=[resp])

        with patch(
            "bouwmeester.api.routes.llm.get_llm_service",
            new=AsyncMock(return_value=mock_service),
        ):
            resp = await client.post(
                "/api/llm/suggest-tags",
                json={"title": "Woningbouw beleid", "node_type": "dossier"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert "woningbouw" in data["matched_tags"]

    @pytest.mark.asyncio
    async def test_summarize_with_mock_provider(self, client):
        """With a mocked LLM service, returns summary."""
        mock_service = DummyLLMService(responses=["Dit is een samenvatting."])

        with patch(
            "bouwmeester.api.routes.llm.get_llm_service",
            new=AsyncMock(return_value=mock_service),
        ):
            resp = await client.post(
                "/api/llm/summarize",
                json={"text": "Heel veel tekst over beleid."},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert data["summary"] == "Dit is een samenvatting."

    @pytest.mark.asyncio
    async def test_suggest_tags_input_validation(self, client):
        """Title exceeding max_length returns 422."""
        resp = await client.post(
            "/api/llm/suggest-tags",
            json={"title": "x" * 501, "node_type": "dossier"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_summarize_input_validation(self, client):
        """Text exceeding max_length returns 422."""
        resp = await client.post(
            "/api/llm/summarize",
            json={"text": "x" * 50001},
        )
        assert resp.status_code == 422
