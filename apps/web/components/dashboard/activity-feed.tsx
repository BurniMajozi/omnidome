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
    <div className="rounded-xl border border-border bg-card p-4 sm:p-5">
      <h3 className="mb-4 text-base font-semibold text-foreground sm:text-lg">Recent Activity</h3>
      <div className="relative border-l border-primary/20 pl-4 ml-3 space-y-5">
        {activities.map((activity) => (
          <div key={activity.id} className="relative flex items-start gap-3 rounded-lg border border-border bg-secondary/20 p-3 hover:bg-secondary/45 transition-colors">
            {/* Dot indicator on timeline */}
            <div className="absolute -left-[22px] top-4 h-2.5 w-2.5 rounded-full bg-primary border-2 border-card" />
            <Avatar className="h-8 w-8 shrink-0">
              <AvatarImage src={`/.jpg?height=32&width=32&query=${activity.user}`} />
              <AvatarFallback className="text-xs bg-primary/10 text-primary font-semibold">{activity.avatar}</AvatarFallback>
            </Avatar>
            <div className="flex-1 space-y-1">
              <p className="text-sm text-foreground leading-snug">
                <span className="font-semibold">{activity.user}</span>{" "}
                <span className="text-muted-foreground">{activity.action}</span>{" "}
                <span className="inline-block rounded bg-primary/10 px-1.5 py-0.5 text-xs font-semibold text-primary">{activity.target}</span>
              </p>
              <p className="text-[10px] font-medium text-muted-foreground">{activity.time}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
