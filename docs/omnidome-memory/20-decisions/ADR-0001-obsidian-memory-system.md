---
type: adr
status: accepted
date: 2026-06-10
area:
  - memory
  - documentation
---

# ADR-0001: Use Obsidian Markdown As OmniDome Project Memory

## Decision

Use `docs/omnidome-memory/` as a tracked, Obsidian-friendly memory system for OmniDome OS.

## Rationale

OmniDome is being built across many services and agent-assisted sessions. The repo needs durable memory that explains not only what exists, but how it got there, what decisions were made, and what remains unresolved.

Plain Markdown works well because it is:

- readable in GitHub and Obsidian;
- diffable in Git;
- easy for agents and humans to update;
- independent of a database or running service.

## Consequences

- Project history should be promoted into `docs/omnidome-memory/`.
- Private or live agent scratch state can remain in gitignored folders such as `Hermes-Obsidian/`.
- Build logs should capture commands, outcomes, affected files, and follow-up questions.
- Long-term decisions should be captured as ADRs under `20-decisions/`.

## Links

- [[../00-index]]
- [[../templates/build-log-template]]
- [[../templates/adr-template]]

