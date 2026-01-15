import { type LucideIcon, ArrowRight } from "lucide-react"
import { Button } from "@/components/ui/button"

interface ModuleCardProps {
  title: string
  description: string
  icon: LucideIcon
  stats: { label: string; value: string }[]
  features: string[]
}

export function ModuleCard({ title, description, icon: Icon, stats, features }: ModuleCardProps) {
  return (
    <div className="group relative rounded-xl border border-border bg-card p-6 transition-all hover:border-primary/50">
      <div className="mb-4 flex items-start justify-between">
        <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
          <Icon className="h-6 w-6 text-primary" />
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
        >
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>

      <h3 className="mb-1 text-lg font-semibold text-foreground">{title}</h3>
      <p className="mb-4 text-sm text-muted-foreground">{description}</p>

      <div className="mb-4 grid grid-cols-2 gap-3">
        {stats.map((stat, i) => (
          <div key={i} className="rounded-lg bg-secondary/50 p-3">
            <p className="text-lg font-bold text-foreground">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        {features.map((feature, i) => (
          <div key={i} className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            {feature}
          </div>
        ))}
      </div>
    </div>
  )
}
