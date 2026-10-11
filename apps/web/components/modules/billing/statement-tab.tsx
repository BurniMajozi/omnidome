"use client"

/** Monthly card-collections statement: what customers paid, OmniDome's fee, what reached your bank, and money out. */

import { useCallback, useEffect, useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { NotConnected } from "@/components/ui/not-connected"
import { getGatewayStatement, type GatewayStatement } from "@/lib/billing-api"
import { fmtMoney } from "@/lib/money"
import type { Loadable } from "@/lib/service-state"
import { Field, Note, inputClass } from "./shared"

const currentPeriod = () => new Date().toISOString().slice(0, 7)

export function StatementTab() {
  const [period, setPeriod] = useState(currentPeriod())
  const [data, setData] = useState<Loadable<GatewayStatement>>({ state: "loading" })
  const [tick, setTick] = useState(0)
  const reload = useCallback(() => setTick((t) => t + 1), [])
  const validPeriod = /^\d{4}-(0[1-9]|1[0-2])$/.test(period)

  useEffect(() => {
    if (!validPeriod) return
    let off = false
    setData({ state: "loading" })
    getGatewayStatement(period).then((l) => !off && setData(l))
    return () => {
      off = true
    }
  }, [period, validPeriod, tick])

  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <CardTitle className="text-base">Statement</CardTitle>
          <Field label="Month" className="w-44">
            <input type="month" className={inputClass} value={period} max={currentPeriod()} onChange={(e) => setPeriod(e.target.value)} />
          </Field>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {!validPeriod ? (
          <Note tone="error">Choose a valid month.</Note>
        ) : data.state === "error" && data.status === 400 ? (
          <Note tone="error">{data.message || "That month is not valid."}</Note>
        ) : data.state !== "ready" ? (
          <NotConnected loadable={data} service="Billing" onRetry={reload} />
        ) : (
          <Body s={data.data} />
        )}
      </CardContent>
    </Card>
  )
}

function Body({ s }: { s: GatewayStatement }) {
  return (
    <div className="space-y-4 text-sm">
      <section className="space-y-1">
        <Line k="Collected from your customers" v={fmtMoney(s.collections.collected_zar)} hint={`${s.collections.charges} card payment${s.collections.charges === 1 ? "" : "s"}`} />
        <Line k="OmniDome gateway fee" v={`-${fmtMoney(s.collections.commission_zar)}`} />
        <Line k="Paid to your bank (you receive)" v={fmtMoney(s.collections.you_receive_zar)} bold />
        <p className="text-xs text-muted-foreground">
          {s.settlement_checks.verified} of {s.settlement_checks.total} payments verified against Paystack.
        </p>
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Refunds" v={`-${fmtMoney(s.refunds.total_zar)}`} hint={`${s.refunds.count} refund${s.refunds.count === 1 ? "" : "s"}`} />
        <Line k="Chargebacks" v={`-${fmtMoney(s.chargebacks.total_zar)}`} hint={`${s.chargebacks.count} lost dispute${s.chargebacks.count === 1 ? "" : "s"}`} />
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Payouts" v={fmtMoney(s.payouts.total_zar)} hint={`${s.payouts.count} payment${s.payouts.count === 1 ? "" : "s"}`} />
        <Line k="Payout fees" v={fmtMoney(s.payouts.fees_zar)} />
      </section>
      <section className="space-y-1 border-t border-border pt-3">
        <Line k="Payout wallet balance" v={fmtMoney(s.payout_wallet_zar)} bold />
        <Line k="Refunds and chargebacks owed to OmniDome" v={fmtMoney(s.open_liabilities_zar)} />
      </section>
    </div>
  )
}

function Line({ k, v, hint, bold }: { k: string; v: string; hint?: string; bold?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 ${bold ? "font-semibold text-foreground" : "text-foreground"}`}>
      <span>
        {k}
        {hint && <span className="ml-2 text-xs font-normal text-muted-foreground">{hint}</span>}
      </span>
      <span className="tabular-nums">{v}</span>
    </div>
  )
}
