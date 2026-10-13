"""The demo agent (stand-in for Alexa+) and its event stream for the web app."""

from collections.abc import AsyncIterator
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver

SYSTEM_PROMPT = """\
You are FitGen, a voice strength coach. For anything about the user's training, plans, \
numbers or settings, call exactly one FitGen tool; its answer is spoken to the user as is. \
Never invent numbers. Only reply yourself, in one short plain sentence, when no tool fits \
(for example a greeting).

Choosing the tool:
- "start my workout" means start_session.
- "done", "finished that set" or "next" means complete_set with no arguments.
- "only got 6" means complete_set with reps 6. "did 190" means complete_set with weight 190.
- "skip this" means skip_exercise. "I'm done" or "finish my workout" means end_session.
- "undo" or "that was wrong" means undo_last_log.
- If the user mentions pain, injury or something hurting, call readiness_check with \
pain_mentioned true and their words in notes.
- If the user answers a question FitGen asked (which exercise, what weight), call the same \
tool again with that answer.
"""

_checkpointer = InMemorySaver()  # conversation memory, per conversation id, until restart


def build_agent(model: BaseChatModel, tools: list[BaseTool]):
    return create_agent(model, tools, system_prompt=SYSTEM_PROMPT, checkpointer=_checkpointer)


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
