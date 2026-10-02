import test from "node:test"
import assert from "node:assert/strict"

const b = await import("./billing-derive.ts")
const money = await import("./money.ts")
const csv = await import("./export-csv.ts")
const api = await import("./api-result.ts")

test("csvCell prefixes formula starters with a single quote", () => {
  for (const s of ["=1+1", "+27821234567", "-5", "@SUM(A1)"]) assert.equal(csv.exportCell(s), `'${s}`)
  assert.equal(csv.exportCell("plain"), "plain")
  assert.equal(csv.exportCell(null), "")
  assert.equal(csv.exportCell(42), "42")
  assert.equal(csv.exportCell(-5), "-5") // real numbers are not formulas
})

test("csvCell quotes commas, quotes and newlines", () => {
  assert.equal(csv.exportCell('a,"b"'), '"a,""b"""')
  assert.equal(csv.exportCell("a\nb"), '"a\nb"')
  // formula starter AND a comma: quote prefix first, then CSV quoting
  assert.equal(csv.exportCell("=A,B"), `"'=A,B"`)
})

test("toCsv adds a BOM and CRLF rows", () => {
  const out = csv.toCsv(["a", "b"], [[1, "=x"]])
  assert.ok(out.startsWith("﻿"))
  assert.equal(out.slice(1), "a,b\r\n1,'=x\r\n")
  assert.equal(csv.toCsv(["a"], [], false), "a\r\n")
})

test("money: decimal strings are exact, floats are rounded to cents", () => {
  assert.equal(money.toCents("1234.50"), 123450)
  assert.equal(money.toCents("0.1") + money.toCents("0.2"), 30)
  assert.equal(money.toCents(0.1 + 0.2), 30)
  assert.equal(money.toCents("-5"), -500)
  assert.equal(money.toCents("1.005"), 101)
  assert.equal(money.toCents("abc"), null)
  assert.equal(money.toCents(null), null)
  assert.equal(money.sumCents(["0.10", 0.2, "x", null]), 30)
})

test("money: fmtMoney formats ZAR with space grouping and comma decimals", () => {
  assert.equal(money.fmtMoney("1234567.8"), "R 1 234 567,80")
  assert.equal(money.fmtMoney(-5), "-R 5,00")
  assert.equal(money.fmtMoney(0), "R 0,00")
  assert.equal(money.fmtMoney(undefined), "—")
  assert.equal(money.sameCents("10.00", 10), true)
  assert.equal(money.sameCents("10.01", 10), false)
})

test("mapAgingBuckets uses the four distinct buckets and ignores legacy rows", () => {
  const rows = [
    { bucket: "current", count: 1, total_zar: "100" },
    { bucket: "1_30", count: 2, total_zar: "200" },
    { bucket: "31_60", count: 3, total_zar: "300" },
    { bucket: "61_90", count: 4, total_zar: "400" },
    { bucket: "90_plus", count: 5, total_zar: "500" },
    { bucket: "30_days", count: 2, total_zar: "200", legacy: true },
    { bucket: "60_days", count: 3, total_zar: "300", legacy: true },
    { bucket: "90_days_plus", count: 9, total_zar: "900", legacy: true },
  ]
  const v = b.mapAgingBuckets(rows)
  assert.deepEqual(v.map((x) => x.key), ["current", "1_30", "31_60", "61_90", "90_plus"])
  assert.deepEqual(v.map((x) => x.label), ["Current", "1-30 days", "31-60 days", "61-90 days", "91+ days"])
  assert.equal(v[0].overdue, false)
  assert.equal(v[4].overdue, true)
})

test("mapAgingBuckets falls back to legacy keys from an older service", () => {
  const v = b.mapAgingBuckets([
    { bucket: "current", count: 1, total_zar: 1 },
    { bucket: "30_days", count: 1, total_zar: 1 },
    { bucket: "60_days", count: 1, total_zar: 1 },
    { bucket: "90_days_plus", count: 1, total_zar: 1 },
  ])
  assert.deepEqual(v.map((x) => x.label), ["Current", "1-30 days", "31-60 days", "61+ days"])
  assert.deepEqual(b.mapAgingBuckets(null), [])
})

test("collectionRateText: null -> N/A, clamped 0..100", () => {
  assert.equal(b.collectionRateText(null), "N/A")
  assert.equal(b.collectionRateText(undefined), "N/A")
  assert.equal(b.collectionRateText("abc"), "N/A")
  assert.equal(b.collectionRateText("87.456"), "87.5%")
  assert.equal(b.collectionRateText(180), "100.0%")
  assert.equal(b.collectionRateText(-3), "0.0%")
  assert.equal(b.collectionRateText(0), "0.0%")
})

test("periodLabel", () => {
  assert.equal(b.periodLabel("2026-09"), "Sep 2026")
  assert.equal(b.periodLabel("junk"), "junk")
  assert.equal(b.periodLabel(null), "")
})

test("describeDunningResult never says 'sent' for skipped or failed actions", () => {
  const np = b.describeDunningResult("skipped_no_provider")
  assert.equal(np.tone, "warning")
  assert.ok(!/^sent$/i.test(np.label) && /not sent/i.test(np.label))
  assert.match(b.describeDunningResult("skipped_suppressed").label, /not sent/i)
  const f = b.describeDunningResult("failed: SMTP 550 mailbox full")
  assert.equal(f.label, "Failed")
  assert.equal(f.tone, "danger")
  assert.equal(f.detail, "SMTP 550 mailbox full")
  assert.equal(b.describeDunningResult("failed").detail, null)
  assert.equal(b.describeDunningResult("sent").tone, "success")
  assert.equal(b.describeDunningResult(null).label, "Pending")
})

test("summariseDunningRun", () => {
  assert.deepEqual(b.summariseDunningRun({ processed: 0, results: {} }), ["Nothing was due."])
  const lines = b.summariseDunningRun({ processed: 3, results: { skipped_no_provider: 2, sent: 1 } })
  assert.equal(lines.length, 2)
  assert.ok(lines.some((l) => /no SMS provider/.test(l) && l.endsWith(": 2")))
})

test("invoiceStatusView: credit_issued is a refund, never 'paid'", () => {
  assert.equal(b.invoiceStatusView("credit_issued").label, "Refund required")
  assert.equal(b.invoiceStatusView("credit_issued").tone, "danger")
  assert.equal(b.invoiceStatusView("paid").label, "Paid")
  assert.equal(b.invoiceStatusView("partially_paid").label, "partially paid")
})

test("invoiceActions: credit notes and voided invoices offer nothing", () => {
  const none = b.invoiceActions({ status: "paid", number: "CN-0001" })
  assert.deepEqual(Object.values(none), [false, false, false, false, false])
  assert.equal(b.invoiceActions({ status: "voided", number: "INV-1" }).void, false)
  const open = b.invoiceActions({ status: "overdue", number: "INV-2" })
  assert.equal(open.pay && open.credit && open.void && open.paystack, true)
  assert.equal(b.invoiceActions({ status: "paid", number: "INV-3" }).pay, false)
})

test("role tiers", () => {
  assert.equal(b.billingTier(null), "none")
  assert.equal(b.billingTier([]), "none")
  assert.equal(b.billingTier(["viewer"]), "reader")
  assert.equal(b.billingTier(["billing_clerk"]), "clerk")
  assert.equal(b.billingTier(["billing_viewer", "finance_admin"]), "admin")
  assert.equal(b.isBillingAdmin(["owner"]), true)
  assert.equal(b.isBillingAdmin(["billing_clerk"]), false)
  assert.equal(b.isBillingClerk(["billing_clerk"]), true)
  assert.equal(b.isBillingClerk(["auditor"]), false)
})

test("customer labels: name from CRM, else short id", () => {
  const names = b.customerNameMap([
    { id: "11111111-aaaa", first_name: "Thandi", last_name: "Nkosi" },
    { id: "22222222-bbbb", first_name: "", last_name: "" },
  ])
  assert.equal(b.customerLabel(names, "11111111-aaaa"), "Thandi Nkosi")
  assert.equal(b.customerLabel(names, "22222222-bbbb"), "Customer 22222222")
  assert.equal(b.shortCustomer("abcdef0123456789"), "Customer abcdef01")
})

test("paymentMix: completed only, shares sum to ~100", () => {
  const mix = b.paymentMix([
    { method: "eft", amount_zar: "300.00", status: "completed" },
    { method: "card", amount_zar: "100.00", status: "completed" },
    { method: "card", amount_zar: "999.00", status: "failed" },
  ])
  assert.deepEqual(mix, [{ name: "eft", value: 75 }, { name: "card", value: 25 }])
  assert.deepEqual(b.paymentMix([]), [])
})

test("showingLabel", () => {
  assert.equal(b.showingLabel(100, 340), "Showing 100 of 340")
  assert.equal(b.showingLabel(20, 20), "Showing all 20")
})

test("readErrorMessage maps statuses and FastAPI detail shapes", () => {
  assert.equal(api.readErrorMessage({ detail: "Invoice has payments" }, 409), "Invoice has payments")
  assert.equal(api.readErrorMessage({ detail: "needs a finance admin role" }, 403), "Not permitted: needs a finance admin role")
  assert.equal(api.readErrorMessage(null, 403), "Not permitted: requires finance admin")
  assert.equal(
    api.readErrorMessage({ detail: [{ loc: ["body", "quantity"], msg: "must be > 0" }] }, 422),
    "quantity: must be > 0",
  )
  assert.equal(api.readErrorMessage(null, 0), "Could not reach the service. Try again.")
  assert.equal(api.readErrorMessage(null, 503), "Service not running")
  assert.equal(api.readErrorMessage({}, 500), "Request failed (HTTP 500)")
})

test("newIdempotencyKey is unique and within the 128 char server limit", () => {
  const a = api.newIdempotencyKey()
  const c = api.newIdempotencyKey()
  assert.notEqual(a, c)
  assert.ok(a.length > 8 && a.length <= 128)
})


test("screen CSV protects whitespace formulas and preserves RFC quoting and decimals", () => {
  assert.equal(b.billingCsv(["Name", "Amount"], [['  =HYPERLINK("x")', "12.34"], ["a,b\nc", -5]]), '\uFEFF"Name","Amount"\r\n"\'  =HYPERLINK(""x"")","12.34"\r\n"a,b\nc","-5"\r\n')
  for (const lead of ["=", "+", "-", "@", "\t", "\r", "\n"]) assert.ok(b.billingCsv(["h"], [[lead + "x"]]).includes('"\''))
})

test("money rejects unsafe amounts and rounds decimal half up for numbers too", () => {
  assert.equal(money.toCents(1.005), 101)
  assert.equal(money.toCents(-1.005), -101)
  assert.equal(money.toCents("9999999999999999999999"), null)
  assert.equal(money.toCents(Infinity), null)
})

test("billing does not assume optional org_admin privilege", () => {
  assert.equal(b.isBillingAdmin(["org_admin"]), false)
  assert.equal(b.isBillingClerk(undefined), false)
})

test("payment mix excludes invalid and negative completed payments", () => {
  assert.deepEqual(b.paymentMix([
    { method: "eft", amount_zar: "10.00", status: "completed" },
    ...["bad", "-10", "0", "99999999999999999999"].map(amount_zar => ({ method: "card", amount_zar, status: "completed" })),
  ]), [{ name: "eft", value: 100 }])
})

test("money aggregate overflow cannot render as a real amount", () => {
  assert.ok(Number.isNaN(money.sumCents(["90071992547409", "90071992547409"])))
  assert.equal(money.fmtMoney(NaN), "—")
})
