import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from "recharts"
import { formatCurrency } from "./utils"

type RevenueRecognitionPoint = {
  period: string
  recognized: number
  deferred: number
  billed: number
}

type RevenueContract = {
  contract: string
  customer: string
  method: string
  start: string
  end: string
  recognized: number
  deferred: number
}

type RevenueRecognitionProps = {
  recognitionSeries: RevenueRecognitionPoint[]
  contracts: RevenueContract[]
}

export function RevenueRecognitionPanel({ recognitionSeries, contracts }: RevenueRecognitionProps) {
  const totals = recognitionSeries.reduce(
    (acc, item) => {
      acc.recognized += item.recognized
      acc.deferred = item.deferred
      acc.billed += item.billed
      return acc
    },
    { recognized: 0, deferred: 0, billed: 0 },
  )

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Revenue Recognition Trend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={recognitionSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="period" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => `R${(v / 1000000).toFixed(1)}M`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                  formatter={(value: number) => formatCurrency(value)}
                />
                <Legend />
                <Area type="monotone" dataKey="recognized" stroke="#34d399" fill="#34d399" fillOpacity={0.25} />
                <Area type="monotone" dataKey="deferred" stroke="#60a5fa" fill="#60a5fa" fillOpacity={0.2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Recognition Snapshot</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm text-muted-foreground">Recognized YTD</p>
            <p className="text-xl font-semibold text-foreground">{formatCurrency(totals.recognized)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Deferred Revenue Balance</p>
            <p className="text-xl font-semibold text-foreground">{formatCurrency(totals.deferred)}</p>
          </div>
          <div>
            <p className="text-sm text-muted-foreground">Billings This Quarter</p>
            <p className="text-xl font-semibold text-foreground">{formatCurrency(totals.billed)}</p>
          </div>
          <div className="rounded-lg border border-border bg-secondary/40 p-3 text-xs text-muted-foreground">
            Recognition methods: Straight-line for subscriptions, milestone for enterprise installs.
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Contract Recognition Schedule</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[780px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Contract</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Customer</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Method</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Start</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">End</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Recognized</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Deferred</th>
                </tr>
              </thead>
              <tbody>
                {contracts.map((contract) => (
                  <tr key={contract.contract} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 text-sm font-medium text-foreground">{contract.contract}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{contract.customer}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{contract.method}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{contract.start}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{contract.end}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(contract.recognized)}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(contract.deferred)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-3">
        <CardHeader>
          <CardTitle className="text-base">Recognized vs Billed</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={recognitionSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="period" stroke="#9ca3af" fontSize={12} />
                <YAxis stroke="#9ca3af" fontSize={12} tickFormatter={(v) => `R${(v / 1000000).toFixed(1)}M`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1f2937", border: "1px solid #374151" }}
                  formatter={(value: number) => formatCurrency(value)}
                />
                <Legend />
                <Bar dataKey="recognized" fill="#34d399" name="Recognized" radius={[4, 4, 0, 0]} />
                <Bar dataKey="billed" fill="#60a5fa" name="Billed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
