import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { formatCurrency } from "./utils"

type BankItem = {
  id: string
  date: string
  description: string
  amount: number
  status: "matched" | "unmatched" | "review"
  source: string
}

type AuditItem = {
  id: string
  user: string
  action: string
  target: string
  time: string
}

type BankReconciliationProps = {
  bankItems: BankItem[]
  auditTrail: AuditItem[]
}

const statusBadge = (status: BankItem["status"]) => {
  switch (status) {
    case "matched":
      return <Badge className="bg-emerald-500/20 text-emerald-400">matched</Badge>
    case "review":
      return <Badge className="bg-amber-500/20 text-amber-400">review</Badge>
    case "unmatched":
      return <Badge className="bg-red-500/20 text-red-400">unmatched</Badge>
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

export function BankReconciliationPanel({ bankItems, auditTrail }: BankReconciliationProps) {
  const matchedCount = bankItems.filter((item) => item.status === "matched").length
  const unmatchedCount = bankItems.filter((item) => item.status === "unmatched").length
  const reviewCount = bankItems.filter((item) => item.status === "review").length

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Bank Reconciliation Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Matched</span>
            <span className="text-sm font-semibold text-foreground">{matchedCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Needs Review</span>
            <span className="text-sm font-semibold text-foreground">{reviewCount}</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">Unmatched</span>
            <span className="text-sm font-semibold text-foreground">{unmatchedCount}</span>
          </div>
          <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
            Auto-matching rules: reference, amount, date +/- 2 days, vendor normalization.
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Bank Statement Items</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Date</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Description</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Source</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Amount</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {bankItems.map((item) => (
                  <tr key={item.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 text-sm text-muted-foreground">{item.date}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{item.description}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{item.source}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(item.amount)}</td>
                    <td className="px-4 py-3 text-right text-sm">{statusBadge(item.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Audit Trail</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {auditTrail.map((entry) => (
              <div key={entry.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <p className="text-sm text-foreground"><span className="font-medium">{entry.user}</span> {entry.action} <span className="font-medium">{entry.target}</span></p>
                  <p className="text-xs text-muted-foreground">{entry.time}</p>
                </div>
                <Badge variant="outline">audit</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
