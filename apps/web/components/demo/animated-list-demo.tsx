"use client"

import { cn } from "@/lib/utils"
import { AnimatedList } from "@/components/ui/animated-list"

interface Item {
  name: string
  description: string
  icon: string
  color: string
  time: string
}

const notifications = [
  {
    name: "New Lead",
    description: "Fibre installation request",
    time: "Just now",
    icon: "👤",
    color: "#6366f1",
  },
  {
    name: "Payment Received",
    description: "R1,299 from Cape Town client",
    time: "2m ago",
    icon: "💳",
    color: "#22c55e",
  },
  {
    name: "Support Ticket",
    description: "High priority: Connection down",
    time: "5m ago",
    icon: "🎫",
    color: "#ef4444",
  },
  {
    name: "New Signup",
    description: "100Mbps Fibre package",
    time: "8m ago",
    icon: "🚀",
    color: "#06b6d4",
  },
  {
    name: "RICA Verified",
    description: "Customer ID confirmed",
    time: "12m ago",
    icon: "✓",
    color: "#10b981",
  },
]

const Notification = ({ name, description, icon, color, time }: Item) => {
  return (
    <figure
      className={cn(
        "relative mx-auto min-h-fit w-full max-w-[400px] cursor-pointer overflow-hidden rounded-xl p-4",
        "bg-slate-800/80 border border-slate-700/50",
        "hover:bg-slate-800 transition-colors"
      )}
    >
      <div className="flex flex-row items-center gap-3">
        <div
          className="flex size-10 items-center justify-center rounded-2xl"
          style={{ backgroundColor: color }}
        >
          <span className="text-lg">{icon}</span>
        </div>
        <div className="flex flex-col overflow-hidden">
          <figcaption className="flex flex-row items-center whitespace-pre text-lg font-medium text-white">
            <span className="text-sm sm:text-lg">{name}</span>
            <span className="mx-1">·</span>
            <span className="text-xs text-slate-400">{time}</span>
          </figcaption>
          <p className="text-sm font-normal text-slate-400">
            {description}
          </p>
        </div>
      </div>
    </figure>
  )
}

export function AnimatedListDemo({ className }: { className?: string }) {
  return (
    <div className={cn("relative flex h-[500px] w-full flex-col p-6 overflow-hidden", className)}>
      <AnimatedList delay={2000}>
        {notifications.map((item, idx) => (
          <Notification {...item} key={idx} />
        ))}
      </AnimatedList>
    </div>
  )
}
