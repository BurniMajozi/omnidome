---
name: obsidian
description: "Read, search, create, and edit notes in the Obsidian vault. Auto-push to GitHub after writing."
version: 1.2.0
author: Hermes Agent
platforms: [linux]
metadata:
  hermes:
    tags: [note-taking, obsidian, documentation, git-sync]
---

# Obsidian Note Vault

## When to Use
- User references "Obsidian", "my notes", "vault", or wants knowledge documented
- Session summaries, architecture summaries, and audit reports should be written here
- Project context that needs to survive across sessions
- Auto-pushing notes to GitHub after writing them

## Vault Location
- **Path:** `/opt/data/home/Documents/Obsidian Vault/OmniDome/` (use absolute path — `~` does NOT expand in `write_file`)
- **Remote:** `https://github.com/BurniMajozi/Hermes-Obsidian.git`
- **Auth format:** `https://oauth2:<PAT>@github.com/user/repo.git` (NOT `https://user:token@`)

## Pushing Changes to GitHub
Always push after writing or editing notes:
```bash
cd /opt/data/home/Documents/Obsidian Vault
git add .
git diff --cached --quiet || git commit -m "<message>"
git push origin main 2>&1 | tail -3
```
The Hermes repo (`BurniMajozi/Hermes`) is SSO-blocked — only the Obsidian repo works with the current PAT.

## Note-Writing Protocol

### File Naming
- Use human-readable names: `Agentic Architecture.md`, `Code Audit Report.md`
- Session notes: `Session YYYY-MM-DD.md`
- Do NOT use timestamps or generic names

### Wikilinks
- Note links use `[[wikilink]]` format (NOT `[text](url)`)
- Example: `[[Agentic Architecture]]`

### Content Rules
- Notes are condensed, interlinked knowledge — NOT raw data dumps
- Each session that produces findings should result in a new note
- Update the Project Index note so it reflects the latest state
- Pointers to detailed files should point to `/opt/data/home/` not the OmniDome project dir
- **NEVER fabricate document content.** If tools can't read a file, say so and ask the user to paste the relevant section

## What Belongs in Obsidian (not memory)
- Stable architecture decisions
- Non-trivial debugging paths / workarounds
- Session summaries / audit reports
- Interlinked project documentation
- UIX/UX design decisions
- To-do lists and priorities
- Integration patterns

## Current Vault Structure
```
OmniDome/
├── Project Index.md          — hub note, all services, current state
├── Agentic Architecture.md   — 5 AI agents, tool registry, reasoning loop
├── Code Audit Report.md      — 16 services, readiness table, gaps
├── Communication Service.md  — chat/messages/tasks API endpoints
├── Communication Hub UIX.md  — all-one-tab interface (6 tabs)
├── Implementation Status.md  — what's done, what's next
├── Remaining Fixes.md        — finance DB, billing R0, marketing security
├── Sales + Marketing Audit.md — sales/marketing findings
├── To-Do List.md             — 20 prioritized tasks
└── Session *.md              — session logs
```

## Handling Issues
- If Hermes repo push fails with auth error → SSO-blocked, skip and report
- If Obsidian vault push fails → `git pull --rebase` then push
- `~` does not expand in `write_file` paths → always use absolute paths
- Home directory on this VM is `/opt/data/home/`, not `/home/hermes/`
