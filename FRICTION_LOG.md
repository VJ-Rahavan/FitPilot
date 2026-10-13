# Friction log

Genuine problems hit with tools, SDKs or docs while building FitGen. Factual only.

## 1. langchain-mcp-adapters installs with mcp 2.x but fails at import

- **Task:** Load the FitGen MCP tools into a LangChain agent for the demo client (Phase 8).
- **Steps:** In a fresh venv, `uv pip install langchain-mcp-adapters mcp==2.3.0`, then
  `import langchain_mcp_adapters.tools`.
- **Expected:** A dependency conflict at install time, or a working import.
- **Actual:** Install succeeds (langchain-mcp-adapters 0.3.1 declares `mcp>=1.24.0` with no
  upper bound), then the import raises `ModuleNotFoundError: No module named
  'mcp.server.fastmcp'`. `langchain_mcp_adapters/tools.py:27-28` imports
  `mcp.server.fastmcp...`, which mcp 2.x removed (FastMCP was renamed MCPServer). The
  adapter also reads `CallToolResult.structuredContent`, while mcp 2.x exposes
  `structured_content`.
- **Severity:** High for anyone on mcp 2.x: the adapter can't be used at all.
- **Workaround:** Wrap the MCP Python SDK's `ClientSession` tools as LangChain
  `StructuredTool`s ourselves (`client/backend/fitgen_client/mcp_tools.py`, about 60 lines),
  returning `(text, structured_content)` with `response_format="content_and_artifact"`.
- **Suggestion:** Cap the dependency at `mcp<2` until mcp 2.x is supported, then switch to
  `mcp.server.mcpserver` and the snake_case result fields.

## 2. langchain-groq pins the Groq SDK below 1.0

- **Task:** Add langchain-groq to the same environment as the FitGen server.
- **Steps:** With `groq>=1.7` already a dependency (used by the server's background insight
  job), run `uv add langchain-groq`.
- **Expected:** Resolves, since both are Groq's own Python packages.
- **Actual:** Unsatisfiable: every langchain-groq 1.1.x requires `groq>=0.30.0,<1.0.0`.
- **Severity:** Medium: forces separate environments or an older Groq SDK.
- **Workaround:** The demo client backend has its own uv project (`client/backend`), which
  uses langchain-groq with Groq SDK 0.37.1; the server keeps Groq SDK 1.7.
- **Suggestion:** Allow `groq>=1` in langchain-groq.
