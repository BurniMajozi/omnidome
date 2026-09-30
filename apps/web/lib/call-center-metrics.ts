/**
 * Pure derivations for the Call Center overview, computed ONLY from real rows
 * returned by the call-center service. Every function returns null / [] when
 * there is nothing to compute so the UI can show "No data yet" instead of
 * inventing a figure. No React / browser imports (node-testable).
 */

export interface CcSession {
  agent_id?: string | null
  direction?: string | null
  start_time?: string | null
  duration_seconds?: number | null
}
export interface CcAgent {
  id: string
  name?: string | null
  extension?: string | null
  status?: string | null
  csat_score?: number | null
}
export interface CcQueue {
  avg_wait_seconds?: number | null
}

/** The service returns plain arrays; older shapes wrapped them ({agents: []}). */
export function unwrapList<T>(v: unknown, key: string): T[] {
  if (Array.isArray(v)) return v as T[]
  const inner = (v as Record<string, unknown> | null | undefined)?.[key]
  return Array.isArray(inner) ? (inner as T[]) : []
}

function sameLocalDay(iso: string, now: Date): boolean {
  const d = new Date(iso)
  return (
    !Number.isNaN(d.getTime()) &&
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  )
}

export function callsToday(sessions: CcSession[], now: Date): number {
  return sessions.filter((s) => s.start_time && sameLocalDay(s.start_time, now)).length
}

export function avgHandleSeconds(sessions: CcSession[]): number | null {
  const d = sessions.map((s) => s.duration_seconds).filter((v): v is number => typeof v === "number")
  return d.length ? d.reduce((a, b) => a + b, 0) / d.length : null
}

export function avgWaitSeconds(queues: CcQueue[]): number | null {
  const w = queues.map((q) => q.avg_wait_seconds).filter((v): v is number => typeof v === "number")
  return w.length ? w.reduce((a, b) => a + b, 0) / w.length : null
}

export function activeAgentCount(agents: CcAgent[]): number {
  return agents.filter((a) => a.status === "active" || a.status === "on_call").length
}

export function formatDuration(sec: number): string {
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

/** Calls per local hour of day (only hours that have calls), split by direction. */
export function hourlyVolume(sessions: CcSession[]): { hour: string; inbound: number; outbound: number }[] {
  const buckets = new Map<number, { inbound: number; outbound: number }>()
  for (const s of sessions) {
    if (!s.start_time) continue
    const d = new Date(s.start_time)
    if (Number.isNaN(d.getTime())) continue
    const h = d.getHours()
    const b = buckets.get(h) ?? { inbound: 0, outbound: 0 }
    if ((s.direction ?? "").toLowerCase() === "outbound") b.outbound += 1
    else b.inbound += 1
    buckets.set(h, b)
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([h, b]) => ({ hour: `${String(h).padStart(2, "0")}:00`, ...b }))
}

export function directionSplit(sessions: CcSession[]): { name: string; value: number }[] {
  let inbound = 0
  let outbound = 0
  for (const s of sessions) {
    if ((s.direction ?? "").toLowerCase() === "outbound") outbound += 1
    else inbound += 1
  }
  return [
    { name: "Inbound", value: inbound },
    { name: "Outbound", value: outbound },
  ].filter((x) => x.value > 0)
}

/** Calls handled = real sessions per agent; satisfaction = the agent's stored csat_score (may be null). */
export function agentPerformance(
  agents: CcAgent[],
  sessions: CcSession[],
  limit = 8,
): { name: string; calls: number; satisfaction: number | null }[] {
  const counts = new Map<string, number>()
  for (const s of sessions) if (s.agent_id) counts.set(s.agent_id, (counts.get(s.agent_id) ?? 0) + 1)
  return agents
    .map((a) => ({
      name: a.name ?? a.extension ?? a.id.slice(0, 8),
      calls: counts.get(a.id) ?? 0,
      satisfaction: typeof a.csat_score === "number" ? a.csat_score : null,
    }))
    .sort((x, y) => y.calls - x.calls)
    .slice(0, limit)
}
