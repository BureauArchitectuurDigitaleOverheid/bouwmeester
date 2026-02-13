"""Claude (Anthropic) LLM provider — capabilities: PUBLIC only."""

import anthropic

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)


class ClaudeLLMService(BaseLLMService):
    """Claude via Anthropic API.

    Only public data (parliamentary items, tag names) should be sent.
    """

    capabilities = ProviderCapabilities(
        allowed_data={DataSensitivity.PUBLIC},
    )

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
