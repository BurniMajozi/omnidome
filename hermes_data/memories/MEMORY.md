OmniDome: 21 microservices. Patches in /opt/data/home/omnidome-patches/. Vault at ~/Documents/Obsidian Vault/OmniDome/ (15+ notes). Git: Hermes-Obsidian ✅ (commit 778fc60). Project NOT pushed — needs new PAT with repo scope for BurniMajozi/omnidome. Vault push pending (terminal restricted — push next session). Session 4: Lifecycle service (port 8018) with 5 tables, sales+journey bridges, health scoring. Frontend: lifecycle-dashboard.tsx + lifecycle-api.ts created.
§
GitHub sync status (2026-05-31):
- BurniMajozi/Hermes-Obsidian ✅ — pushed, up to date with 8 notes
- BurniMajozi/Hermes ⚠️ — remote exists but push auth fails (old repo, wrong content)
- git remote URL format that works: https://oauth2:ghp_FS...Fxfd@github.com/...
- PAT: ghp_FS...Fxfd (classic, repo scope)
§
Obsidian vault updated 2026-06-01: Added Session 2026-06-01.md, updated Implementation Status.md and To-Do List.md. Pushed to BurniMajozi/Hermes-Obsidian (commit 4610fe1). Vault at /opt/data/home/Documents/Obsidian Vault/OmniDome/ — 14 notes total.
§
Session 4 (2026-06-01): Built Lifecycle Service (port 8018) — customer lifecycle tracking with 5 models (LifecycleStage, LifecycleEvent, CustomerLifecycle, CustomerSegmentAssignment, LifecycleSummary), sales bridge (from-sale on deal close-won), journey bridge (from-journey on cancel outcomes), health scoring (0-100), churn probability tracking. Frontend API client at apps/web/lib/lifecycle-api.ts. Total microservices now 21. Integration points still to wire: sales close-won → lifecycle, journey respond → lifecycle, CRM 360 → lifecycle context. Vault notes and skill updated.
§
Vault pushed 2026-06-01: Session 4 notes + Implementation Status updated (commit 778fc60). OmniDome now has 21 microservices. Lifecycle service (port 8018) built with 5 tables, cross-service bridges to journey engine + sales. Files unchanged since last read in vault at /opt/data/home/Documents/Obsidian Vault/OmniDome/.