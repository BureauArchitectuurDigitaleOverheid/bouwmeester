"""VLAM (Dutch government sovereign LLM) provider — OpenAI-compatible API.

Capabilities: PUBLIC + INTERNAL + CONFIDENTIAL (sovereign, government-operated).
"""

from openai import AsyncOpenAI

from bouwmeester.services.llm.base import (
    BaseLLMService,
    DataSensitivity,
    ProviderCapabilities,
)


class VlamLLMService(BaseLLMService):
    """VLAM via OpenAI-compatible API.

    Government-operated, so all data sensitivity levels are permitted.
    """

    capabilities = ProviderCapabilities(
        allowed_data={
            DataSensitivity.PUBLIC,
            DataSensitivity.INTERNAL,
            DataSensitivity.CONFIDENTIAL,
        },
    )

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def _complete(self, prompt: str, max_tokens: int = 1024) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or ""
