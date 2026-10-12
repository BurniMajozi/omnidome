export interface WorkJob {
  id: string; agent_type: string; objective: string; goal_label: string | null; status: string
  parent_job_id?: string | null; thread_id?: string | null
  max_cost_usd: number; estimated_cost_usd: number; actual_cost_usd: number | null
  cost_source: string; total_steps: number; total_tokens: number; created_at: string; error: string | null
  result?: { final_output?: string }; context_used?: { memory_status?: string; memory_recalled?: boolean; skills?: string[] }
  activity?: { text: string; updated_at: string; items: { id: string; title: string; kind: string; status: string; result_summary?: string; started_at?: string }[] } | null
  model_calls?: { model: string; provider: string }[]
}
export interface WorkThread { id: string; title: string; turns: WorkJob[] }
export interface WorkAgent { id: string; employee_id: string; agent_type: string; name: string; role: string; monthly_budget_usd: number; month_spend_usd: number; status: string }
export interface WorkBudget { monthly_budget_usd: number | null; month_spend_usd: number; day_spend_usd?: number; daily_budget_usd?: number }
export const running = (status: string) => ["queued", "running", "pause_requested"].includes(status)
export const needsReview = (status: string) => ["awaiting_hitl", "awaiting_review", "interrupted", "failed", "stopped_by_ceiling", "max_iterations", "dead_letter"].includes(status)
export const workLabel = (status: string) => ({ awaiting_review: "Ready for your feedback", awaiting_hitl: "Needs approval", stopped_by_ceiling: "Budget or step limit", pause_requested: "Pausing after this turn", max_iterations: "Needs review", dead_letter: "Needs recovery" }[status] || status.replaceAll("_", " "))
export const usd = (value: number) => value.toLocaleString("en-ZA", { style: "currency", currency: "USD", maximumFractionDigits: value > 0 && value < 0.01 ? 4 : 2 })
export async function workApi<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const response = await fetch(`/api/orchestrator/agents${path}`, { cache: "no-store", ...(body !== undefined ? { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`)
  return data
}
export function workConversations(jobs: WorkJob[]) {
  const index = new Map(jobs.map(j => [j.id, j]))
  const groups = new Map<string, { id: string; title: string; latest: WorkJob; count: number }>()
  for (const job of jobs) {
    let root = job; const visited = new Set<string>()
    while (root.parent_job_id && index.has(root.parent_job_id) && !visited.has(root.id)) { visited.add(root.id); root = index.get(root.parent_job_id)! }
    const id = job.thread_id || root.parent_job_id || root.id
    const group = groups.get(id)
    if (group) group.count++
    else groups.set(id, { id, title: root.goal_label || root.objective, latest: job, count: 1 })
  }
  return [...groups.values()]
}
