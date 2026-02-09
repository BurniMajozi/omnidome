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
    <div className="group relative rounded-xl border border-border bg-card p-4 transition-all hover:border-primary/50 sm:p-6">
      <div className="mb-4 flex items-start justify-between">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 sm:h-12 sm:w-12">
          <Icon className="h-5 w-5 text-primary sm:h-6 sm:w-6" />
        </div>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100"
        >
          <ArrowRight className="h-4 w-4" />
        </Button>
      </div>

      <h3 className="mb-1 text-base font-semibold text-foreground sm:text-lg">{title}</h3>
      <p className="mb-4 text-sm text-muted-foreground">{description}</p>

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {stats.map((stat, i) => (
          <div key={i} className="rounded-lg bg-secondary/50 p-3">
            <p className="text-base font-bold text-foreground sm:text-lg">{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.label}</p>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        {features.map((feature, i) => (
          <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground sm:text-sm">
            <div className="h-1.5 w-1.5 rounded-full bg-primary" />
            {feature}
          </div>
        ))}
      </div>
    </div>
  )
}
