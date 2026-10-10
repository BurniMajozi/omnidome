"use client"
import { BookOpen, Brain, Database, Hand, ShieldCheck, Sparkles, Wrench, Zap, type LucideIcon } from "lucide-react"

const ICONS: Record<string, LucideIcon> = {
  memory: Brain,
  knowledge: BookOpen,
  data: Database,
  skill: Sparkles,
  tool: Wrench,
  verify: ShieldCheck,
  approval: Hand,
  reasoning: Zap,
}

export function StepKindIcon({ kind, className }: { kind: string; className?: string }) {
  const Icon = ICONS[kind] ?? Wrench
  return <Icon className={className} aria-hidden="true" />
}
