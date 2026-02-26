import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { formatCurrency } from "./utils"

type ReceiptItem = {
  id: string
  vendor: string
  amount: number
  category: string
  status: "queued" | "processed" | "flagged"
  ocrConfidence: number
  submittedBy: string
  date: string
}

type ApprovalItem = {
  id: string
  request: string
  amount: number
  owner: string
  status: "pending" | "approved" | "rejected"
  policy: string
}

type PurchaseOrder = {
  id: string
  vendor: string
  amount: number
  status: "draft" | "review" | "approved" | "sent"
  approver: string
  dueDate: string
}

type AssetItem = {
  id: string
  asset: string
  location: string
  status: "active" | "maintenance" | "retired"
  cost: number
  depreciation: number
  remainingLife: string
}

type RecurringPayment = {
  id: string
  vendor: string
  amount: number
  frequency: string
  nextRun: string
  status: "active" | "paused"
}

type ExpenseTrackingProps = {
  receipts: ReceiptItem[]
  approvals: ApprovalItem[]
  purchaseOrders: PurchaseOrder[]
  assets: AssetItem[]
  recurringPayments: RecurringPayment[]
}

const statusBadge = (status: string) => {
  switch (status) {
    case "processed":
    case "approved":
    case "sent":
    case "active":
      return <Badge className="bg-emerald-500/20 text-emerald-400">{status}</Badge>
    case "review":
    case "pending":
      return <Badge className="bg-amber-500/20 text-amber-400">{status}</Badge>
    case "flagged":
    case "rejected":
    case "paused":
      return <Badge className="bg-red-500/20 text-red-400">{status}</Badge>
    case "draft":
      return <Badge className="bg-blue-500/20 text-blue-400">{status}</Badge>
    default:
      return <Badge variant="secondary">{status}</Badge>
  }
}

export function ExpenseTrackingPanel({
  receipts,
  approvals,
  purchaseOrders,
  assets,
  recurringPayments,
}: ExpenseTrackingProps) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Receipt OCR Queue</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {receipts.map((receipt) => (
              <div key={receipt.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{receipt.vendor}</p>
                  <p className="text-xs text-muted-foreground">{receipt.category} · {receipt.date}</p>
                  <p className="text-xs text-muted-foreground">Submitted by {receipt.submittedBy}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-foreground">{formatCurrency(receipt.amount)}</p>
                  <p className="text-xs text-muted-foreground">OCR {receipt.ocrConfidence}%</p>
                  {statusBadge(receipt.status)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Travel & Delegation Approvals</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {approvals.map((approval) => (
              <div key={approval.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{approval.request}</p>
                  <p className="text-xs text-muted-foreground">Owner: {approval.owner}</p>
                  <p className="text-xs text-muted-foreground">Policy: {approval.policy}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-foreground">{formatCurrency(approval.amount)}</p>
                  {statusBadge(approval.status)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card lg:col-span-2">
        <CardHeader>
          <CardTitle className="text-base">Purchase Orders Workflow</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[720px]">
              <thead>
                <tr className="border-b border-border bg-secondary/50">
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">PO</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Vendor</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Approver</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Due</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Amount</th>
                  <th className="px-4 py-3 text-right text-sm font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {purchaseOrders.map((po) => (
                  <tr key={po.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 text-sm font-medium text-foreground">{po.id}</td>
                    <td className="px-4 py-3 text-sm text-foreground">{po.vendor}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{po.approver}</td>
                    <td className="px-4 py-3 text-sm text-muted-foreground">{po.dueDate}</td>
                    <td className="px-4 py-3 text-right text-sm text-foreground">{formatCurrency(po.amount)}</td>
                    <td className="px-4 py-3 text-right text-sm">{statusBadge(po.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Asset Register</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {assets.map((asset) => (
              <div key={asset.id} className="rounded-lg border border-border bg-secondary/30 p-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-foreground">{asset.asset}</p>
                    <p className="text-xs text-muted-foreground">{asset.location} · {asset.remainingLife}</p>
                  </div>
                  <div className="text-right">
                    {statusBadge(asset.status)}
                    <p className="text-xs text-muted-foreground">Depreciation {formatCurrency(asset.depreciation)}</p>
                  </div>
                </div>
                <div className="mt-2 text-sm text-muted-foreground">Cost {formatCurrency(asset.cost)}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card className="border-border bg-card">
        <CardHeader>
          <CardTitle className="text-base">Recurring Payments</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {recurringPayments.map((payment) => (
              <div key={payment.id} className="flex items-center justify-between rounded-lg border border-border bg-secondary/30 p-3">
                <div>
                  <p className="text-sm font-medium text-foreground">{payment.vendor}</p>
                  <p className="text-xs text-muted-foreground">{payment.frequency} · Next: {payment.nextRun}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-semibold text-foreground">{formatCurrency(payment.amount)}</p>
                  {statusBadge(payment.status)}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

