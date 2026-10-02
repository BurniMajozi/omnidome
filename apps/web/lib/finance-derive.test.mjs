import test from "node:test"
import assert from "node:assert/strict"

const f = await import("./finance-derive.ts")

test("finance tiers", () => {
  assert.equal(f.financeTier(null), "none")
  assert.equal(f.financeTier(["org_user"]), "reader")
  assert.equal(f.financeTier(["accountant"]), "clerk")
  assert.equal(f.financeTier(["auditor", "finance_admin"]), "admin")
  assert.equal(f.isFinanceAdmin(["accountant"]), false)
  assert.equal(f.isFinanceClerk(["accountant"]), true)
  assert.equal(f.isFinanceClerk(["auditor"]), false)
})

test("journalTotals balances in integer cents (no float drift)", () => {
  const t = f.journalTotals([{ debit: 0.1 }, { debit: 0.2 }, { credit: 0.3 }])
  assert.equal(t.debit, 30)
  assert.equal(t.credit, 30)
  assert.equal(t.balanced, true)
  assert.equal(f.journalTotals([{ debit: 100 }, { credit: 99.99 }]).balanced, false)
  assert.equal(f.journalTotals([]).balanced, false)
  assert.equal(f.journalTotals([{ debit: "10.00" }, { credit: "10" }]).balanced, true)
})

test("periodOf / isPeriodClosed", () => {
  assert.equal(f.periodOf("2026-09-14"), "2026-09")
  assert.equal(f.periodOf("bad"), null)
  const periods = [{ period: "2026-08", status: "closed" }, { period: "2026-09", status: "open" }]
  assert.equal(f.isPeriodClosed(periods, "2026-08"), true)
  assert.equal(f.isPeriodClosed(periods, "2026-09"), false)
  assert.equal(f.isPeriodClosed(periods, null), false)
  assert.equal(f.isPeriodClosed(null, "2026-08"), false)
})

test("ledgerIsEmpty: all-zero figures are not real", () => {
  const zero = { revenue: 0, expenses: 0, ebit: 0, cash_position: 0 }
  assert.equal(f.ledgerIsEmpty(zero, 0), true)
  assert.equal(f.ledgerIsEmpty(zero, null), true)
  assert.equal(f.ledgerIsEmpty({ ...zero, cash_position: 5 }, 0), false)
  assert.equal(f.ledgerIsEmpty(zero, 12), false)
  assert.equal(f.ledgerIsEmpty(null, 0), true)
})

test("scenarioBase: null with nothing posted, else real figures only", () => {
  assert.equal(f.scenarioBase(null, 0), null)
  assert.equal(f.scenarioBase({ revenue: 0, expenses: 0, ebit: 0, cash_position: 9 }, -5), null)
  assert.deepEqual(f.scenarioBase({ revenue: 1000, expenses: 400, ebit: 600, cash_position: 0 }, -250), { revenue: 1000, opex: 400, capex: 250 })
  assert.deepEqual(f.scenarioBase({ revenue: 1000, expenses: 400, ebit: 600, cash_position: 0 }, 80), { revenue: 1000, opex: 400, capex: 0 })
})


test("journal validation rejects discarded, negative, mixed and nonfinite lines", () => {
  const debit = { account_code: "1000", debit: 10, credit: 0 }
  const credit = { account_code: "4000", debit: 0, credit: 10 }
  assert.equal(f.validJournalLines([debit, credit]), true)
  assert.equal(f.validJournalLines([{ ...debit, account_code: "" }, credit]), false)
  assert.equal(f.validJournalLines([{ ...debit, debit: -10 }, { ...credit, credit: -10 }]), false)
  assert.equal(f.validJournalLines([{ ...debit, debit: NaN }, credit]), false)
  assert.equal(f.validJournalLines([{ ...debit, debit: 11, credit: 1 }, credit]), false)
  assert.equal(f.journalTotals([{ debit: -5 }, { credit: -5 }]).balanced, false)
})

test("journal sources preserve backend source keys and unknown sources", () => {
  assert.equal(f.journalSourceLabel("finance.reversal"), "Reversal")
  assert.equal(f.journalSourceLabel("billing.invoice"), "Billing invoice")
  assert.equal(f.journalSourceLabel("custom.source"), "custom.source")
  assert.equal(f.journalSourceLabel(null), "Unspecified")
})

test("journals reject zero, mixed sides, unsafe totals and invalid periods", () => {
  assert.equal(f.journalTotals([{ debit: 10, credit: 10 }, {}]).balanced, false)
  assert.equal(f.journalTotals([{ debit: 10 }, { credit: 10 }, {}]).balanced, false)
  assert.equal(f.journalTotals([{ debit: 1e20 }, { credit: 1e20 }]).balanced, false)
  assert.equal(f.periodOf("2026-13-01"), null)
  assert.equal(f.periodOf("2026-00"), null)
})


test("journal line rounding matches backend Decimal half up", () => {
  assert.equal(f.journalTotals([{ debit: "1.005" }, { credit: "1.01" }]).balanced, true)
  assert.equal(f.journalTotals([{ debit: 1.005 }, { credit: 1.01 }]).balanced, true)
})
