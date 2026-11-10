# Architecture decision records

Each ADR captures one significant decision: its context, the choice, and the consequences. ADRs are immutable once accepted. To change course, write a new ADR that supersedes the old one.

| #    | Decision                                                                    | Status   |
| ---- | --------------------------------------------------------------------------- | -------- |
| 0001 | [Record architecture decisions](0001-record-architecture-decisions.md)      | Accepted |
| 0002 | [Hexagonal architecture for the core service](0002-hexagonal-architecture.md) | Accepted |
| 0003 | [Local-first, zero-cost AI stack](0003-local-first-zero-cost-stack.md)      | Accepted |
| 0004 | [Python core service + WebSocket voice transport](0004-websocket-voice-transport.md) | Accepted |
| 0005 | [Tauri for the desktop shell](0005-tauri-desktop-shell.md)                  | Accepted |
| 0006 | [Sentence streaming and playback acknowledgements](0006-sentence-streaming-and-playback-acks.md) | Accepted (amended by 0009) |
| 0007 | [Bounded tool-calling loop](0007-tool-calling-agent-loop.md) | Accepted |
| 0008 | [SQLite persistence](0008-sqlite-persistence.md) | Accepted |
| 0009 | [Barge-in and playback watchdog](0009-barge-in-and-playback-watchdog.md) | Accepted |
| 0010 | [Voice ID](0010-voice-id.md) | Accepted |

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```
