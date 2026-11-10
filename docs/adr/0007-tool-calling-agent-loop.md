# 0007. Bounded tool-calling loop with errors returned to the model

- Status: Accepted
- Date: 2026-11-10

## Context

Phase 3 lets the LLM act through tools: tasks, reminders, memory, weather, search, MCP. Small local models make mistakes. They call tools that don't exist, pass malformed arguments, or loop. Voice turns must always end, quickly, with something spoken.

## Decision

- Native tool calling through Ollama's `/api/chat` `tools` parameter. Tool calls stream as `ToolCall` events next to `TextDelta`s.
- `Brain.respond` runs at most `max_tool_rounds` (default 4) model calls with tools. The final call offers **no** tools, which forces a spoken answer.
- `ToolRegistry.execute` never raises. Unknown tools, `ToolError`, unexpected exceptions and timeouts (20 s) become `"Error: …"` tool results, so the model can recover ("I couldn't find that task, which one did you mean?").
- Tools return short plain-text facts, not JSON, because small models paraphrase prose more reliably.
- No agent framework (LangChain, LangGraph, …). The loop is about 60 lines, fully typed and fully tested.

## Consequences

- **+** Turns are bounded, and failures are conversational rather than fatal.
- **+** Any OpenAI-style tool-calling model works through the same port. MCP tools plug into the same registry.
- **−** Sequential tool execution. Parallel calls are rare for a personal assistant and could be added later.
- **−** Tool descriptions consume context tokens. The guide recommends enabling only the MCP servers you use.
