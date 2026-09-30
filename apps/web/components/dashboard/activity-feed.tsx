"use client"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { loadCrmActivities } from "@/lib/ops-api"
import { CRM_ACTIVITIES_KEY, useSharedOps } from "@/lib/overview-api"
import { initials, toActivityItems } from "@/lib/overview-derive"

/** Recent CRM activity events (real rows from /svc/crm/customers/activities). */
export function ActivityFeed() {
  const { value, reload } = useSharedOps(CRM_ACTIVITIES_KEY, loadCrmActivities)
  const items = value.state === "ready" ? toActivityItems(value.data).slice(0, 8) : []

  return (
    <div className="rounded-xl border border-border bg-card p-4 sm:p-5">
      <h3 className="mb-4 text-base font-semibold text-foreground sm:text-lg">Recent Activity</h3>
      {value.state !== "ready" ? (
        <NotConnected loadable={value} service="CRM" onRetry={reload} />
      ) : items.length === 0 ? (
        <NoDataYet message="No activity yet" />
      ) : (
        <div className="relative ml-3 space-y-5 border-l border-primary/20 pl-4">
          {items.map((activity) => (
            <div
              key={activity.id}
              className="relative flex items-start gap-3 rounded-lg border border-border bg-secondary/20 p-3 transition-colors hover:bg-secondary/45"
            >
              <div className="absolute -left-[22px] top-4 h-2.5 w-2.5 rounded-full border-2 border-card bg-primary" />
              <Avatar className="h-8 w-8 shrink-0">
                <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">
                  {initials(activity.user)}
                </AvatarFallback>
              </Avatar>
              <div className="flex-1 space-y-1">
                <p className="text-sm leading-snug text-foreground">
                  {activity.user && <span className="font-semibold">{activity.user}</span>}{" "}
                  <span className="text-muted-foreground">{activity.action}</span>{" "}
                  {activity.target && (
                    <span className="inline-block rounded bg-primary/10 px-1.5 py-0.5 text-xs font-semibold text-primary">
                      {activity.target}
                    </span>
                  )}
                </p>
                {activity.time && <p className="text-[10px] font-medium text-muted-foreground">{activity.time}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
