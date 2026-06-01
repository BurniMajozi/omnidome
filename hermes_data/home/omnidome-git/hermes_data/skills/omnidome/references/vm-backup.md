# OmniDome — VM Backup & Daily Sync

> Setup for daily VM state backup to GitHub. Configured 2026-05-31.

## GitHub Repos

| Repo | URL | Purpose |
|------|-----|---------|
| Hermes | `BurniMajozi/Hermes` | VM setup backup (restoration script, configs) |
| Hermes-Obsidian | `BurniMajozi/Hermes-Obsidian` | Obsidian vault notes |
| omnidome | `BurniMajozi/omnidome` | Main project code |

## Daily Backup — Cron Job

- **Schedule:** 12:00 AM CAT (UTC+2) = 22:00 UTC daily
- **Job type:** no_agent (script-only, verbatim stdout delivery)
- **Delivery:** to Telegram (current chat)

### What Gets Backed Up

1. **Hermes repo** (`BurniMajozi/Hermes`):
   - `VM-SETUP.md` — regenerated from current VM state
   - `scripts/restore.sh` — updated restoration script
   - `opt-data/config.yaml` — Hermes config (sanitized)
   - `omnidome-patches/` — all new service implementations
   - `Obsidian Vault/` — all notes

2. **Hermes-Obsidian repo** (`BurniMajozi/Hermes-Obsidian`):
   - All OmniDome notes wikilinked together

## Backup Script Location

`/opt/data/home/scripts/daily-backup.sh`

## Restoration

If VM is lost:
```bash
git clone https://github.com/BurniMajozi/Hermes.git ~/hermes-backup
cd ~/hermes-backup
sudo bash scripts/restore.sh
```

See `VM-SETUP.md` in the Hermes repo for full restoration steps.

## PAT Auth Note

GitHub no longer accepts password auth. User must create a PAT:
1. GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)
2. Generate with `repo` scope
3. Provide token to agent for remote setup

PAT is a ONE-TIME setup. After that, cron jobs push automatically.
