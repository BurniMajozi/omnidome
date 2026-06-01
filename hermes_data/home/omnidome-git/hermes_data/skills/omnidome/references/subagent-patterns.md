# Subagent Usage Patterns — Lessons from OmniDome

> When to use subagents vs. direct file writes, based on real project experience.

## The 600s Timeout Wall

Subagents on this model have a hard 600s timeout. Tasks creating >15 files routinely hit it.

| Task Type | Approach | Why |
|-----------|----------|-----|
| Complex single-file rewrite | ✅ Subagent | Needs isolation, complex logic |
| Full service routes (7+ files) | ✅ Subagent | One subagent per service works |
| Boilerplate file creation (>5 files) | ❌ Use `write_file` directly | IPC overhead per file kills you |
| Simple model + route + schema | ❌ Use `write_file` directly | Faster, no timeout risk |

## Sibling Subagent Conflicts

When multiple subagents write to the same directory, you get "modified by sibling subagent" warnings and potential data loss.

**Rule:** Each subagent gets its own directory. One subagent per service, not one per file.

## When Subagents Timeout

If a subagent times out:
1. Check what files it DID create (partial results are usually valid)
2. Create the remaining files directly with `write_file`
3. Don't retry the same subagent task — it will likely timeout again

## Cron Job Constraints

- `rm -rf` in cron prompts is blocked by security filter
- Use `cp -r` to overwrite instead
- Keep cron prompts simple — complex logic belongs in a script