# 0011. Route tools per request and keep the prompt prefix stable

- Status: Accepted
- Date: 2026-11-10
- Amends: [0007](0007-tool-calling-agent-loop.md)

## Context

After Phase 3, turns took 17–28 s on a CPU-only laptop with `llama3.2:3b`. Measured against Ollama on that machine:

| Request | Tools attached | Prompt tokens | Prompt time | Total |
| --- | --- | --- | --- | --- |
| "Add buy milk to my tasks" | all 12 | 993 | 15.5 s | 17.2 s |
| same | the 3 task tools | 466 | 4.6 s | 5.5 s |
| "Fun fact about owls" | none | 213 | 1.3 s | 2.8 s |
| same | all 12 | 995 | 16.1 s | 17.1 s |

Prompt processing, not generation, dominates. Each tool description costs roughly 65 tokens, about 1 s on CPU. With all tools attached, the model also made spurious calls (it ran `recall` for the owl question). Separately, the system prompt contained the time down to the minute, so its text changed every minute and Ollama couldn't reuse its prompt cache across turns.

## Decision

- **`ToolRouter`** (`application/tools/routing.py`) attaches only the tool *groups* a request plausibly needs:
    1. keyword patterns per group, matched against the request;
    2. if none match, the same patterns against **the previous user message**, so vague follow-ups ("and call dad too") keep their tools without dragging old topics into new requests;
    3. if still nothing matches and an embedding model is available, the best-matching group description above a similarity threshold;
    4. otherwise, no tools. The system prompt then explains that tools attach on demand, so the model answers from knowledge, or suggests a phrasing instead of claiming it can't do things.
- Patterns favour recall over precision: an extra group costs about 150 tokens, while a missing one costs a wrong answer.
- MCP servers get a group automatically, triggered by the server name or words from its tool names.
- `JARVIS_TOOL_ROUTING=all` restores the old behaviour, which is useful on a GPU or for debugging.
- **Stable prefix:** the system prompt carries only the date and the part of the day. Variable content (the tool instruction line and memories) goes last. Exact times come from `get_current_time`, and reminders compute times themselves.

## Consequences

- **+** Measured end to end through the service on the same CPU: chit-chat 17 s → **2.3 s**; tool turns 17–30 s → **6.6–8.9 s** (each needs two model calls plus the tool itself). Fewer tools on offer also means fewer wrong calls.

| Request | Groups attached | Total |
| --- | --- | --- |
| "Tell me a fun fact about owls" | none | 2.3 s |
| "Add buy milk to my tasks" | tasks | 7.6 s |
| "Actually, mark it done" | tasks | 6.6 s |
| "What's the weather in Manila?" | weather | 8.9 s |
| "Who was Ada Lovelace?" | encyclopedia | 7.5 s |
- **+** Deterministic and unit-tested. The embedding fallback degrades to "no tools" if the model is missing.
- **−** A request phrased with no recognised cue gets no tools. Mitigations: the embedding fallback, the previous-message context, and a prompt that suggests a working phrasing. Patterns are easy to extend.
- **−** The model no longer sees the exact minute unless it asks the time tool.
