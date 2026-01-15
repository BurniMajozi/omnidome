import { Badge } from "@/components/ui/badge"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

const tickets = [
  {
    id: "#12847",
    subject: "Internet connectivity issue",
    customer: "John Smith",
    priority: "High",
    status: "Open",
    assignee: "SC",
  },
  {
    id: "#12846",
    subject: "Router configuration help",
    customer: "Emily Brown",
    priority: "Medium",
    status: "In Progress",
    assignee: "MJ",
  },
  {
    id: "#12845",
    subject: "Speed upgrade request",
    customer: "Tech Corp",
    priority: "Low",
    status: "Pending",
    assignee: "ED",
  },
  {
    id: "#12844",
    subject: "Billing inquiry",
    customer: "Lisa Wang",
    priority: "Medium",
    status: "Resolved",
    assignee: "AT",
  },
]

const priorityColors = {
  High: "bg-destructive/20 text-destructive",
  Medium: "bg-chart-3/20 text-chart-3",
  Low: "bg-primary/20 text-primary",
}

const statusColors = {
  Open: "bg-destructive/20 text-destructive",
  "In Progress": "bg-chart-2/20 text-chart-2",
  Pending: "bg-chart-3/20 text-chart-3",
  Resolved: "bg-primary/20 text-primary",
}

export function TicketsTable() {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border p-5">
        <h3 className="text-lg font-semibold text-foreground">Recent Tickets</h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border text-left">
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">ID</th>
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Subject</th>
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Customer</th>
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Priority</th>
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Status</th>
              <th className="px-5 py-3 text-xs font-medium uppercase text-muted-foreground">Assignee</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((ticket) => (
              <tr key={ticket.id} className="border-b border-border last:border-0 hover:bg-secondary/30">
                <td className="px-5 py-4 text-sm font-medium text-primary">{ticket.id}</td>
                <td className="px-5 py-4 text-sm text-foreground">{ticket.subject}</td>
                <td className="px-5 py-4 text-sm text-muted-foreground">{ticket.customer}</td>
                <td className="px-5 py-4">
                  <Badge variant="secondary" className={priorityColors[ticket.priority as keyof typeof priorityColors]}>
                    {ticket.priority}
                  </Badge>
                </td>
                <td className="px-5 py-4">
                  <Badge variant="secondary" className={statusColors[ticket.status as keyof typeof statusColors]}>
                    {ticket.status}
                  </Badge>
                </td>
                <td className="px-5 py-4">
                  <Avatar className="h-7 w-7">
                    <AvatarImage src={`/.jpg?height=28&width=28&query=${ticket.assignee}`} />
                    <AvatarFallback className="text-xs">{ticket.assignee}</AvatarFallback>
                  </Avatar>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
