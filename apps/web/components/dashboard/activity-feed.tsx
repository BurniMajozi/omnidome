import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"

const activities = [
  {
    id: 1,
    user: "Sarah Chen",
    action: "closed ticket",
    target: "#12847",
    time: "2 min ago",
    avatar: "SC",
  },
  {
    id: 2,
    user: "Mike Johnson",
    action: "added new lead",
    target: "Tech Corp",
    time: "15 min ago",
    avatar: "MJ",
  },
  {
    id: 3,
    user: "Emily Davis",
    action: "resolved outage",
    target: "Node-42",
    time: "1 hour ago",
    avatar: "ED",
  },
  {
    id: 4,
    user: "Alex Thompson",
    action: "completed call",
    target: "Customer #9821",
    time: "2 hours ago",
    avatar: "AT",
  },
  {
    id: 5,
    user: "Lisa Wang",
    action: "launched campaign",
    target: "Q1 Promo",
    time: "3 hours ago",
    avatar: "LW",
  },
]

export function ActivityFeed() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h3 className="mb-4 text-lg font-semibold text-foreground">Recent Activity</h3>
      <div className="space-y-4">
        {activities.map((activity) => (
          <div key={activity.id} className="flex items-start gap-3">
            <Avatar className="h-8 w-8">
              <AvatarImage src={`/.jpg?height=32&width=32&query=${activity.user}`} />
              <AvatarFallback className="text-xs">{activity.avatar}</AvatarFallback>
            </Avatar>
            <div className="flex-1 space-y-1">
              <p className="text-sm text-foreground">
                <span className="font-medium">{activity.user}</span>{" "}
                <span className="text-muted-foreground">{activity.action}</span>{" "}
                <span className="font-medium text-primary">{activity.target}</span>
              </p>
              <p className="text-xs text-muted-foreground">{activity.time}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
