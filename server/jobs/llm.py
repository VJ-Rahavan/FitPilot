"""LLM clients for background jobs. Never called on the request path.

`LLM_PROVIDER` picks the implementation: Groq (default) or Amazon Bedrock (Converse API).
Both apply a per-call timeout and retry transient failures.
"""

import asyncio
from typing import Protocol

from server.config import Settings


class LLMError(RuntimeError):
    """The model call failed after retries, or returned nothing usable."""


class LLMClient(Protocol):
    model_id: str

    async def complete(self, *, system: str, user: str, max_tokens: int = 600) -> str:
        """One system + user turn; returns the model's text."""
        ...


class GroqClient:
    def __init__(
        self,
        *,
        api_key: str,
        model_id: str,
        timeout: float,
        max_retries: int,
        http_client=None,
    ):
        from groq import AsyncGroq  # imported here so Bedrock-only deployments don't need it

        self.model_id = model_id
        self._client = AsyncGroq(
            api_key=api_key, timeout=timeout, max_retries=max_retries, http_client=http_client
        )

    async def complete(self, *, system: str, user: str, max_tokens: int = 600) -> str:
        from groq import GroqError

        kwargs = {}
        if self.model_id.startswith("openai/gpt-oss"):
            # Reasoning models: keep reasoning short and out of the returned text.
            kwargs = {"reasoning_effort": "low", "include_reasoning": False}
        try:
            response = await self._client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_completion_tokens=max_tokens,
                temperature=0.4,
                **kwargs,
            )
        except GroqError as exc:
            raise LLMError(f"Groq call failed: {type(exc).__name__}: {exc}") from exc
        text = (response.choices[0].message.content or "").strip() if response.choices else ""
        if not text:
            raise LLMError("Groq returned an empty response")
        return text


class BedrockClient:
    def __init__(
        self, *, model_id: str, region: str, timeout: float, max_retries: int, client=None
    ):
        self.model_id = model_id
        if client is None:
            import boto3
            from botocore.config import Config

            client = boto3.client(
                "bedrock-runtime",
                region_name=region,
                config=Config(
                    connect_timeout=min(timeout, 5.0),
                    read_timeout=timeout,
                    retries={"max_attempts": max_retries + 1, "mode": "standard"},
                ),
            )
        self._client = client

    async def complete(self, *, system: str, user: str, max_tokens: int = 600) -> str:
        from botocore.exceptions import BotoCoreError, ClientError

        def call() -> dict:
            return self._client.converse(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": user}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.4},
            )

        try:
            response = await asyncio.to_thread(call)  # boto3 is synchronous
        except (BotoCoreError, ClientError) as exc:
            raise LLMError(f"Bedrock call failed: {exc}") from exc
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        text = "".join(b.get("text", "") for b in blocks).strip()
        if not text:
            raise LLMError("Bedrock returned an empty response")
        return text


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "bedrock":
        return BedrockClient(
            model_id=settings.bedrock_model_id,
            region=settings.aws_region,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")
    return GroqClient(
        api_key=settings.groq_api_key,
        model_id=settings.groq_model_id,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )
