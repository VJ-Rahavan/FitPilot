"""The demo agent (stand-in for Alexa+) and its event stream for the web app."""

from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelRetryMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

SYSTEM_PROMPT = """\
You are FitGen, a voice strength coach. Every turn, call exactly one tool. FitGen's tools \
do things and answer with the exact words to speak. Only FitGen tools can log, start, end, \
save or change anything, so never say any of that happened unless a tool just did it. Use \
the reply tool only for greetings, small talk, or a short question when you can't tell \
what the user wants. Never invent numbers or coaching advice.

Choosing the tool:
- "start my workout" means start_session. "end workout", "I'm done", "I'm finished" or \
"finish my workout" means end_session.
- "done", "finished that set", "next" or "log set" means complete_set with no arguments.
- "only got 6" means complete_set with reps 6. "did 190" means complete_set with weight 190.
- If they say how the set felt while logging it, pass effort: easy ("easy", "too light"), \
ok ("felt good", "solid"), hard ("tough", "rough"), failed ("brutal", "barely", "couldn't \
finish"). If they only describe a set they already logged, don't log another set.
- "skip this" means skip_exercise. "undo" or "that was wrong" means undo_last_log.
- "how do I ..." means get_form_cues, even if the exercise name is vague: FitGen asks \
which one was meant.
- If the user mentions pain, injury or something hurting, call readiness_check with \
pain_mentioned true and their words in notes.
- If the user answers a question FitGen asked (which exercise, what weight), call the same \
tool again with that answer.
"""

KEEP_TURNS = 3  # recent user turns sent to the model; FitGen's server holds the real state

_checkpointer = InMemorySaver()  # conversation memory, per conversation id, until restart


class VoiceTurnMiddleware(AgentMiddleware):
    """Every model call must pick a tool, and sees only the last few turns.

    Forcing a tool stops the model from imitating FitGen's replies ("Set 2 of 4 done.")
    without actually calling the tool. Trimming keeps each request small, which matters on
    rate-limited model tiers; FitGen's server, not the chat history, holds workout state.
    """

    def _prepare(self, request: ModelRequest) -> ModelRequest:
        return request.override(messages=recent_turns(request.messages), tool_choice="any")

    def wrap_model_call(self, request, handler):
        return handler(self._prepare(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._prepare(request))


def recent_turns(messages: list[BaseMessage], keep: int = KEEP_TURNS) -> list[BaseMessage]:
    """The messages from the `keep`-th last user message on (never splitting a tool call)."""
    human_indexes = [i for i, m in enumerate(messages) if isinstance(m, HumanMessage)]
    if len(human_indexes) <= keep:
        return messages
    return messages[human_indexes[-keep] :]


def _reply_tool() -> StructuredTool:
    async def reply(text: str) -> tuple[str, dict[str, Any]]:
        return text, {"components": [], "display": "fragment", "is_error": False}

    return StructuredTool(
        name="reply",
        description=(
            "Say something short to the user when no FitGen tool fits: a greeting, small talk, "
            "or a question when you can't tell what they want. Never use it to say a set was "
            "logged, a workout started or ended, or anything was saved or changed."
        ),
        args_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "One short sentence"}},
            "required": ["text"],
        },
        coroutine=reply,
        response_format="content_and_artifact",
        return_direct=True,
    )


# Groq's errors when the model's output was malformed (about 3% of live turns with gpt-oss:
# a made-up "commentary" tool, or unparseable output). Asking again almost always works.
_MALFORMED_GENERATION = ("tool call validation failed", "parsing failed", "failed_generation")


def is_invalid_tool_call(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _MALFORMED_GENERATION)


def build_agent(model: BaseChatModel, tools: list[BaseTool]):
    return create_agent(
        model,
        [*tools, _reply_tool()],
        system_prompt=SYSTEM_PROMPT,
        middleware=[
            VoiceTurnMiddleware(),
            ModelRetryMiddleware(
                max_retries=2,
                retry_on=is_invalid_tool_call,
                on_failure="error",
                initial_delay=0.2,
                backoff_factor=1.0,
                jitter=False,
            ),
        ],
        checkpointer=_checkpointer,
    )


def _text_of(content: Any) -> str:
    """Message content as plain text (providers send a string or a list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


async def stream_events(agent, message: str, conversation_id: str) -> AsyncIterator[dict]:
    """Agent run → events for the web app:

    text {delta}; tool_start {id, name, args}; tool_result {id, name, text, components,
    display, is_error}; done {conversation_id, text} where text is the final spoken reply.
    """
    config = {"configurable": {"thread_id": conversation_id}}
    names: dict[str, str] = {}
    final_text = ""
    tool_texts: list[str] = []  # with return_direct tools, these are the spoken reply
    async for mode, chunk in agent.astream(
        {"messages": [HumanMessage(message)]}, config=config, stream_mode=["updates", "messages"]
    ):
        if mode == "messages":
            msg, meta = chunk
            if isinstance(msg, AIMessageChunk) and meta.get("langgraph_node") == "model":
                if delta := _text_of(msg.content):
                    yield {"event": "text", "data": {"delta": delta}}
            continue
        for update in chunk.values():
            for msg in (update or {}).get("messages", []):
                if isinstance(msg, AIMessage):
                    for call in msg.tool_calls:
                        names[call["id"]] = call["name"]
                        yield {
                            "event": "tool_start",
                            "data": {"id": call["id"], "name": call["name"], "args": call["args"]},
                        }
                    if not msg.tool_calls:
                        final_text = _text_of(msg.content).strip()
                elif isinstance(msg, ToolMessage):
                    artifact = msg.artifact or {}
                    tool_texts.append(_text_of(msg.content))
                    yield {
                        "event": "tool_result",
                        "data": {
                            "id": msg.tool_call_id,
                            "name": names.get(msg.tool_call_id, msg.name or ""),
                            "text": _text_of(msg.content),
                            "components": artifact.get("components", []),
                            "display": artifact.get("display", "fragment"),
                            "is_error": artifact.get("is_error", msg.status == "error"),
                        },
                    }
    spoken = final_text or " ".join(t for t in tool_texts if t)
    yield {"event": "done", "data": {"conversation_id": conversation_id, "text": spoken}}
