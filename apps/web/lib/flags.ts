/**
 * Feature flags for gating not-yet-production-ready UI.
 *
 * Each flag reads a NEXT_PUBLIC_* env var and defaults to OFF, so mock/unwired
 * surfaces stay hidden unless a deployment explicitly opts in. Set the var to
 * "true" (or "1") in apps/web/.env to enable.
 *
 * NEXT_PUBLIC_* vars are inlined at build time, so these are safe to read in
 * client components.
 */

function flagEnabled(value: string | undefined): boolean {
  if (!value) return false
  const v = value.trim().toLowerCase()
  return v === "true" || v === "1" || v === "yes" || v === "on"
}

/**
 * Mock "Journals & Trial Balance" panel in the Finance module. Superseded by
 * LiveJournalEntries (real backend). Off by default; enable to show the legacy
 * mock panel alongside the live one. (Decision 2026-07-24: feature-flag off.)
 */
export const FINANCE_MOCK_JOURNALS_ENABLED = flagEnabled(
  process.env.NEXT_PUBLIC_ENABLE_FINANCE_MOCK_JOURNALS,
)

/**
 * A/B Testing module (journey-ab-testing). Pure mock data, no backend wiring
 * yet. Off by default so v1 doesn't ship a fake-working feature. (Decision
 * 2026-07-24: feature-flag off for v1.)
 */
export const AB_TESTING_ENABLED = flagEnabled(
  process.env.NEXT_PUBLIC_ENABLE_AB_TESTING,
)
