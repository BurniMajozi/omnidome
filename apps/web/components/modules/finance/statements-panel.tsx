import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { formatCurrency } from "./utils"

type StatementLine = {
  label: string
  amount: number
  style?: "section" | "subtotal" | "total" | "line"
  indent?: boolean
}

type StatementsPanelProps = {
  balanceSheet: StatementLine[]
  incomeStatement: StatementLine[]
  cashFlow: StatementLine[]
}

const lineClass = (style?: StatementLine["style"]) => {
  switch (style) {
    case "section":
      return "font-semibold text-foreground"
    case "subtotal":
      return "font-semibold text-foreground"
    case "total":
      return "font-bold text-foreground"
    default:
      return "text-foreground"
  }
}

function StatementTable({ lines }: { lines: StatementLine[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[640px]">
        <tbody>
          {lines.map((line, idx) => (
            <tr key={`${line.label}-${idx}`} className="border-b border-border last:border-0">
              <td className={`px-4 py-3 text-sm ${lineClass(line.style)} ${line.indent ? "pl-8 text-muted-foreground" : ""}`}>
                {line.label}
              </td>
              <td className={`px-4 py-3 text-right text-sm ${lineClass(line.style)}`}>
                {line.style === "section" && line.amount === 0 ? "" : formatCurrency(line.amount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function StatementsPanel({ balanceSheet, incomeStatement, cashFlow }: StatementsPanelProps) {
  return (
    <Card className="border-border bg-card">
      <CardHeader>
        <CardTitle className="text-base">Financial Statements (GAAP)</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="balance" className="w-full">
          <TabsList className="bg-secondary">
            <TabsTrigger value="balance">Balance Sheet</TabsTrigger>
            <TabsTrigger value="income">Income Statement</TabsTrigger>
            <TabsTrigger value="cash">Cash Flow</TabsTrigger>
          </TabsList>
          <TabsContent value="balance" className="mt-4">
            <StatementTable lines={balanceSheet} />
          </TabsContent>
          <TabsContent value="income" className="mt-4">
            <StatementTable lines={incomeStatement} />
          </TabsContent>
          <TabsContent value="cash" className="mt-4">
            <StatementTable lines={cashFlow} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}
