import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { formatCurrency } from "./utils"

type JournalEntry = {
  id: string
  date: string
  account: string
  description: string
  debit: number
  credit: number
  source: string
}

type TrialBalanceLine = {
  id: string
  account: string
  debit: number
  credit: number
}

type JournalsTrialBalanceProps = {
  journals: JournalEntry[]
  trialBalance: TrialBalanceLine[]
}

export function JournalsTrialBalancePanel({ journals, trialBalance }: JournalsTrialBalanceProps) {
  const totals = trialBalance.reduce(
    (acc, line) => {
      acc.debit += line.debit
      acc.credit += line.credit
      return acc
    },
    { debit: 0, credit: 0 },
  )

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Itemized Journals</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[860px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Date</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Account</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Description</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Source</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Debit</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Credit</th>
                </tr>
              </thead>
              <tbody>
                {journals.map((entry) => (
                  <tr key={entry.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 text-sm text-muted-foreground">{entry.date}</td>
                    <td className="px-4 py-3 text-sm font-medium text-foreground">{entry.account}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{entry.description}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{entry.source}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(entry.debit)}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(entry.credit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Trial Balance (GAAP)</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Account</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Debit</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Credit</th>
                </tr>
              </thead>
              <tbody>
                {trialBalance.map((line) => (
                  <tr key={line.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 text-sm text-foreground">{line.account}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(line.debit)}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(line.credit)}</td>
                  </tr>
                ))}
                <tr className="border-t border-border bg-secondary/40">
                  <td className="px-4 py-3 text-sm font-semibold text-foreground">Totals</td>
                  <td className="px-4 py-3 text-right text-sm font-semibold text-foreground">{formatCurrency(totals.debit)}</td>
                  <td className="px-4 py-3 text-right text-sm font-semibold text-foreground">{formatCurrency(totals.credit)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Trial balance is balanced with debit totals equal to credit totals.</p>
        </CardContent>
      </Card>
    </div>
  )
}
