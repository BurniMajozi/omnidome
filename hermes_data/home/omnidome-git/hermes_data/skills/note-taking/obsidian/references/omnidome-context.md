# OmniDome Project Context

> Reference for the `obsidian` and other project skills. Updated 2026-06-01.

## What is OmniDome?

Carrier-grade ISP operating system for South African fibre providers. 18 microservices, agentic AI layer, unified communication hub.

**Author:** Bene Majozi (BurniMajozi) — Cell C SA, Data Scientist, Doctorate student
**Repo:** `BurniMajozi/omnidome` (main code on GitHub)
**Vault:** `BurniMajozi/Hermes-Obsidian` (Obsidian notes)

## Key Conventions

| Convention | Value |
|-----------|-------|
| **Home directory** | `/opt/data/home/` (NOT `/home/hermes/` or `~`) |
| **Writeable patch dir** | `/opt/data/home/omnidome-patches/` (project dir owned by different user) |
| **Obsidian vault** | `/opt/data/home/Documents/Obsidian Vault/OmniDome/` |
| **Obsidian links** | `[[wikilink]]` format, no file extensions |
| **Git auth** | `https://oauth2:<PAT>@github.com/user/repo.git` |
| **SSO-blocked repos** | `BurniMajozi/Hermes` |
| **Working repos** | `BurniMajozi/Hermes-Obsidian`, `BurniMajozi/omnidome` |

## User Preferences

- **Concise responses**: Lead with the answer, details after
- **Parallel implementation**: Create multiple services/files in parallel
- **Direct, execution-focused**: "Build and report", not "shall I proceed?"
- **One-tab UIX**: Everything in a single tabbed interface

## Obsidian Notes to Update After Each Session

1. Session note — what was done, decisions made
2. To-Do List.md — update priorities
3. Implementation Status.md — update service readiness
4. Project Index.md — keep high-level view current