"""Chat model for the demo agent, picked by LLM_PROVIDER: Groq (default) or Bedrock."""

from langchain_core.language_models.chat_models import BaseChatModel

from fitgen_client.config import ClientSettings


class ModelNotConfigured(RuntimeError):
    pass


def build_chat_model(settings: ClientSettings) -> BaseChatModel:
    if settings.llm_provider == "bedrock":
        from langchain_aws import ChatBedrockConverse

        # TODO(Phase 9): also limit Bedrock to one tool call per turn once tested live.
        return ChatBedrockConverse(
            model=settings.bedrock_chat_model_id,
            region_name=settings.aws_region,
            temperature=0.3,
        )
    if not settings.groq_api_key:
        raise ModelNotConfigured("GROQ_API_KEY is not set")
    from langchain_groq import ChatGroq

    # One tool per turn: tools end the turn (return_direct), so a second parallel call
    # could act on something the user didn't ask for.
    extra: dict = {"parallel_tool_calls": False}
    reasoning: dict = {}
    if settings.groq_model_id.startswith("openai/gpt-oss"):
        # Same options the server's insight job uses with these models (verified live).
        reasoning = {"reasoning_effort": "low"}
        extra["include_reasoning"] = False
    return ChatGroq(
        model=settings.groq_model_id,
        api_key=settings.groq_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
        temperature=0.3,
        # Groq counts the maximum possible answer against the tokens-per-minute limit, so
        # an uncapped request stalls after a few quick turns on the free tier (measured:
        # 8 back-to-back turns took 31 s uncapped, 7 s capped). A tool call needs < 100.
        max_tokens=300,
        model_kwargs=extra,
        **reasoning,
    )
