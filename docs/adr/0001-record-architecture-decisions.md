# 0001. Record architecture decisions

- Status: Accepted
- Date: 2026-11-10

## Context

Jarvis OS will grow over many months in phases: voice, brain, dashboard, mobile. Without a record, the reasons behind early choices get lost, and they get re-litigated or broken by accident.

## Decision

Keep lightweight Architecture Decision Records (after Michael Nygard) in `docs/adr/`, numbered sequentially and published in the docs site.

## Consequences

- Every significant structural or technology choice gets a short ADR in the same PR.
- ADRs are append-only. Changing a decision means a new ADR marked as superseding the old one.
