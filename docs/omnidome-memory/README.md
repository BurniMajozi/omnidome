# OmniDome Memory

This folder is an Obsidian-friendly project memory for OmniDome OS.

Use it as the durable history of how the system was built: architecture decisions, module status, build logs, incident notes, deployment notes, and agent coordination rules.

## Vault Setup

Open the repository root or this `docs/omnidome-memory` folder as an Obsidian vault.

Recommended Obsidian settings:

- Files and links: use Markdown links.
- New link format: shortest path when possible.
- Default location for new notes: same folder as current file.
- Daily notes folder: `10-build-log`.
- Templates folder: `templates`.

## Memory Rules

- Keep operational secrets out of memory notes.
- Link decisions to the affected modules.
- Log what changed, why it changed, and how it was verified.
- Use one note per meaningful build session or incident.
- Keep Hermes/private agent working state in `Hermes-Obsidian/` if needed; that folder is gitignored and should not be treated as the project source of truth.

## Main Entry Points

- [[00-index]]
- [[10-build-log/2026-06-10-compliance-wiring-and-agent-isolation]]
- [[20-decisions/ADR-0001-obsidian-memory-system]]
- [[20-decisions/ADR-0002-agent-protocol-architecture]]
- [[30-modules/compliance]]
- [[30-modules/agent-orchestration]]
- [[30-modules/tenant-memory]]
