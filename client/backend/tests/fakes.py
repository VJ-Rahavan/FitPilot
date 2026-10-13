"""A scripted chat model: replies in order, records what it was sent."""

import json
from collections.abc import Iterator
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult


def tool_call(name: str, args: dict, call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class ScriptedChatModel(BaseChatModel):
    replies: list[AIMessage]
    seen: list[list[BaseMessage]] = []
    bind_kwargs: list[dict] = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedChatModel":
        self.bind_kwargs.append({"tools": [getattr(t, "name", t) for t in tools], **kwargs})
        return self

    def _next(self, messages: list[BaseMessage]) -> AIMessage:
        self.seen.append(list(messages))
        return self.replies.pop(0)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next(messages))])

    def _stream(
        self, messages, stop=None, run_manager=None, **kwargs
    ) -> Iterator[ChatGenerationChunk]:
        reply = self._next(messages)
        if reply.tool_calls:
            call = reply.tool_calls[0]
            chunk = {
                "name": call["name"],
                "args": json.dumps(call["args"]),
                "id": call["id"],
                "index": 0,
            }
            yield ChatGenerationChunk(message=AIMessageChunk(content="", tool_call_chunks=[chunk]))
        else:
            words = reply.content.split(" ")
            for i, word in enumerate(words):
                sep = " " if i < len(words) - 1 else ""
                yield ChatGenerationChunk(message=AIMessageChunk(content=word + sep))
