"use client"

/**
 * OKF Skills panel (docs/skills.md): reusable, versioned procedural knowledge for agents.
 * Tabs: Platform library (shipped, read-only) / My organisation / Mine (private).
 * Skills are guidance only: they never add tools or skip approvals. Instructions are rendered as escaped text.
 */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Copy,
  Download,
  GitFork,
  Loader2,
  Lock,
  Pencil,
  Plus,
  Search,
  Share2,
  ThumbsDown,
  ThumbsUp,
  Upload,
  X,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  activateSkill,
  createSkill,
  deprecateSkill,
  exportSkill,
  forkSkill,
  getSkillsMeta,
  getSkillVersions,
  importSkill,
  listAgents,
  listSkills,
  previewSkillImport,
  sendSkillFeedback,
  shareSkill,
  transferOKFSkill,
  updateSkill,
  type OKFSkill,
  type SkillImportPreview,
  type SkillInputDef,
  type SkillSafety,
  type SkillScope,
  type SkillsMeta,
  type SkillToolInfo,
  type SkillVersionRow,
  type SkillWriteInput,
} from "@/lib/orchestrator-api"

type Tab = "platform" | "organisation" | "mine"

const SAFETY_LABEL: Record<SkillSafety, string> = {
  read_only: "Reads only",
  drafts_only: "Drafts only",
  can_act: "Can act (approvals apply)",
}
const SAFETY_STYLE: Record<SkillSafety, string> = {
  read_only: "border-emerald-500/30 text-emerald-500",
  drafts_only: "border-sky-500/30 text-sky-500",
  can_act: "border-amber-500/40 text-amber-500",
}
const SCOPE_LABEL: Record<SkillScope, string> = {
  platform: "Platform",
  tenant: "Organisation",
  team: "Team",
  user: "Private",
}
const MAX_IMPORT_BYTES = 40_000

function when(iso?: string | null): string {
  if (!iso) return "never"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "never" : d.toLocaleString("en-ZA", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })
}

// ── Escaped markdown (no HTML is ever injected) ──────────────────────────────

function inline(text: string): ReactNode[] {
  return text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i} className="rounded bg-muted px-1 py-px font-mono text-[11px]">{part.slice(1, -1)}</code>
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    return <Fragment key={i}>{part}</Fragment>
  })
}

export function SafeMarkdown({ text }: { text: string }) {
  const blocks: ReactNode[] = []
  let list: string[] = []
  let ordered = false
  const flush = () => {
    if (!list.length) return
    const items = list.map((li, i) => <li key={i}>{inline(li)}</li>)
    blocks.push(ordered ? <ol key={blocks.length} className="ml-5 list-decimal space-y-0.5">{items}</ol> : <ul key={blocks.length} className="ml-5 list-disc space-y-0.5">{items}</ul>)
    list = []
  }
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd()
    const head = /^(#{1,4})\s+(.*)$/.exec(line)
    const bullet = /^\s*[-*]\s+(.*)$/.exec(line)
    const number = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (head) {
      flush()
      blocks.push(<h4 key={blocks.length} className="mt-3 text-xs font-semibold text-foreground">{inline(head[2])}</h4>)
    } else if (bullet || number) {
      const isOrdered = !bullet
      if (list.length && ordered !== isOrdered) flush()
      ordered = isOrdered
      list.push((bullet ?? number)![1])
    } else if (!line.trim()) {
      flush()
    } else {
      flush()
      blocks.push(<p key={blocks.length}>{inline(line)}</p>)
    }
  }
  flush()
  return <div className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">{blocks}</div>
}

// ── Editor ───────────────────────────────────────────────────────────────────

interface Draft {
  skill_name: string
  description: string
  instructions: string
  category: string
  safety_class: SkillSafety
  scope: SkillScope
  target_agent_types: string[]
  tools_required: string[]
  tools_optional: string[]
  triggers: string
  tags: string
  inputs: SkillInputDef[]
  visibility_roles: string
  changelog: string
}

const EMPTY: Draft = {
  skill_name: "", description: "", instructions: "", category: "operational", safety_class: "read_only", scope: "user",
  target_agent_types: [], tools_required: [], tools_optional: [], triggers: "", tags: "", inputs: [], visibility_roles: "", changelog: "",
}

const lines = (v: string) => v.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)

function fromSkill(s: OKFSkill): Draft {
  return {
    skill_name: s.skill_name, description: s.description, instructions: s.instructions || s.guidance_prompt, category: s.category,
    safety_class: s.safety_class, scope: s.scope, target_agent_types: s.target_agent_types, tools_required: s.tools_required,
    tools_optional: s.tools_optional ?? [], triggers: (s.triggers ?? []).join("\n"), tags: (s.tags ?? []).join(", "), inputs: s.inputs ?? [],
    visibility_roles: (s.visibility_roles ?? []).join(", "), changelog: "",
  }
}

export function validateDraft(d: Draft, tools: SkillToolInfo[]): string[] {
  const errs: string[] = []
  const byName = new Map(tools.map((t) => [t.name, t]))
  if (d.skill_name.trim().length < 2) errs.push("Give the skill a name.")
  if (d.description.trim().length < 10) errs.push("Describe when to use it (at least 10 characters, start with \"Use when ...\").")
  if (d.instructions.trim().length < 20) errs.push("Instructions need at least 20 characters: steps, rules and the output format.")
  const unknown = d.tools_required.filter((n) => !byName.has(n))
  if (unknown.length) errs.push(`Unknown tools: ${unknown.join(", ")}.`)
  const acting = d.tools_required.filter((n) => byName.get(n)?.mutates)
  if (acting.length && d.safety_class !== "can_act") errs.push(`${acting.join(", ")} change data. Set the safety class to "Can act" or remove them.`)
  const names = d.inputs.map((i) => i.name.trim())
  if (names.some((n) => !/^[A-Za-z][A-Za-z0-9_]*$/.test(n))) errs.push("Input names must start with a letter and use letters, digits or underscores.")
  if (new Set(names).size !== names.length) errs.push("Input names must be unique.")
  if (d.scope === "team" && !lines(d.visibility_roles).length) errs.push("Name at least one role for a team skill.")
  return errs
}

function toPayload(d: Draft): SkillWriteInput {
  return {
    skill_name: d.skill_name.trim(), description: d.description.trim(), instructions: d.instructions.trim(), category: d.category,
    safety_class: d.safety_class, scope: d.scope === "platform" ? "tenant" : d.scope, target_agent_types: d.target_agent_types,
    tools_required: d.tools_required, tools_optional: d.tools_optional, triggers: lines(d.triggers), tags: lines(d.tags),
    inputs: d.inputs.map((i) => ({ ...i, name: i.name.trim() })), visibility_roles: lines(d.visibility_roles),
    changelog: d.changelog.trim() || undefined,
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-medium text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="mt-0.5 text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  )
}

const selectCls = "mt-1 h-8 w-full rounded-md border border-border bg-background px-2 text-xs"

function SkillEditor({ meta, initial, editing, onCancel, onSaved }: {
  meta: SkillsMeta
  initial: Draft
  editing: OKFSkill | null
  onCancel: () => void
  onSaved: (s: OKFSkill, note: string) => void
}) {
  const [d, setD] = useState<Draft>(initial)
  const [toolQuery, setToolQuery] = useState("")
  const [saving, setSaving] = useState(false)
  const [serverError, setServerError] = useState<string | null>(null)
  const errors = useMemo(() => validateDraft(d, meta.tools), [d, meta.tools])
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setD((prev) => ({ ...prev, [key]: value }))
  const toggle = (key: "target_agent_types" | "tools_required" | "tools_optional", value: string) =>
    setD((prev) => ({ ...prev, [key]: prev[key].includes(value) ? prev[key].filter((v) => v !== value) : [...prev[key], value] }))
  const visibleTools = meta.tools.filter((t) => !toolQuery || t.name.toLowerCase().includes(toolQuery.toLowerCase()))

  const save = async () => {
    setSaving(true)
    setServerError(null)
    try {
      const payload = toPayload(d)
      const saved = editing ? await updateSkill(editing.id, payload) : await createSkill(payload)
      const needsAdmin = saved.status === "draft" && saved.scope !== "user"
      onSaved(saved, needsAdmin ? "Saved as a draft. An admin has to activate it before agents use it." : editing ? "Skill updated." : "Skill created.")
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Could not save the skill")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold">{editing ? `Edit ${editing.skill_name}` : "New skill"}</h3>
      {editing && editing.status !== "draft" && (
        <p className="text-[11px] text-muted-foreground">Saving creates a new version. The current one stays in the history.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="Name"><Input value={d.skill_name} onChange={(e) => set("skill_name", e.target.value)} placeholder="Weekly KPI brief" className="mt-1 h-8 text-xs" /></Field>
        <Field label="Category">
          <select value={d.category} onChange={(e) => set("category", e.target.value)} className={selectCls}>
            {meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Field>
        <Field label="Safety class" hint="Drafts-only skills produce text a person sends. Can-act skills still go through approvals.">
          <select value={d.safety_class} onChange={(e) => set("safety_class", e.target.value as SkillSafety)} className={selectCls}>
            {meta.safety_classes.map((c) => <option key={c} value={c} disabled={c === "can_act" && !meta.caller.admin}>{SAFETY_LABEL[c]}{c === "can_act" && !meta.caller.admin ? " (admin only)" : ""}</option>)}
          </select>
        </Field>
      </div>
      <Field label="When to use it" hint="This is what the agent matches against the user's request. Start with &quot;Use when ...&quot;.">
        <textarea value={d.description} onChange={(e) => set("description", e.target.value)} rows={2} maxLength={800} className="mt-1 w-full rounded-md border border-border bg-background p-2 text-xs" />
      </Field>
      <Field label="Instructions (markdown)" hint="Steps, decision rules, output format and guardrails. Only the selected skills are shown to the agent, within a token budget.">
        <textarea value={d.instructions} onChange={(e) => set("instructions", e.target.value)} rows={12} maxLength={12000} className="mt-1 w-full rounded-md border border-border bg-background p-2 font-mono text-[11px]" />
      </Field>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label="Triggers (one per line)" hint="Phrases or intents that should bring this skill up.">
          <textarea value={d.triggers} onChange={(e) => set("triggers", e.target.value)} rows={3} className="mt-1 w-full rounded-md border border-border bg-background p-2 text-xs" />
        </Field>
        <div className="space-y-3">
          <Field label="Tags (comma separated)"><Input value={d.tags} onChange={(e) => set("tags", e.target.value)} className="mt-1 h-8 text-xs" /></Field>
          <Field label="Share with">
            <select value={d.scope} onChange={(e) => set("scope", e.target.value as SkillScope)} className={selectCls} disabled={!!editing}>
              <option value="user">Only me (private)</option>
              <option value="tenant">{meta.caller.admin ? "My organisation" : "My organisation (submitted as a draft for an admin)"}</option>
              {meta.caller.admin && <option value="team">Specific roles</option>}
            </select>
          </Field>
          {d.scope === "team" && (
            <Field label="Roles that can see it (comma separated)"><Input value={d.visibility_roles} onChange={(e) => set("visibility_roles", e.target.value)} className="mt-1 h-8 text-xs" /></Field>
          )}
        </div>
      </div>
      <Field label="Applies to agents" hint="Empty means every internal agent. The customer-facing agent only gets skills that name it.">
        <div className="mt-1 flex flex-wrap gap-1.5">
          {meta.agent_types.map((a) => (
            <label key={a} className={`cursor-pointer rounded border px-2 py-0.5 text-[11px] ${d.target_agent_types.includes(a) ? "border-primary bg-primary/10 text-primary" : "border-border text-muted-foreground"}`}>
              <input type="checkbox" className="sr-only" checked={d.target_agent_types.includes(a)} onChange={() => toggle("target_agent_types", a)} />{a}
            </label>
          ))}
        </div>
      </Field>
      <Field label="Tools" hint={meta.tools_source === "snapshot" ? "Tool list is a snapshot: the live registry could not be read." : "Picked from the live tool registry. Required tools must be on the agent, otherwise the skill is skipped. Optional tools are used when present."}>
        <Input value={toolQuery} onChange={(e) => setToolQuery(e.target.value)} placeholder="Filter tools" className="mt-1 mb-1.5 h-7 text-xs" />
        <div className="max-h-44 divide-y divide-border overflow-y-auto rounded-md border border-border">
          {visibleTools.map((t) => (
            <div key={t.name} className="flex items-center justify-between gap-2 px-2 py-1 text-[11px]">
              <span className="min-w-0 truncate font-mono" title={t.description}>
                {t.name}
                {t.requires_approval ? <span className="ml-1 text-red-400">approval</span> : t.mutates ? <span className="ml-1 text-amber-400">changes data</span> : null}
              </span>
              <span className="flex shrink-0 gap-3">
                <label className="flex items-center gap-1"><input type="checkbox" checked={d.tools_required.includes(t.name)} onChange={() => toggle("tools_required", t.name)} />required</label>
                <label className="flex items-center gap-1"><input type="checkbox" checked={d.tools_optional.includes(t.name)} onChange={() => toggle("tools_optional", t.name)} />optional</label>
              </span>
            </div>
          ))}
          {!visibleTools.length && <p className="p-2 text-[11px] text-muted-foreground">No tool matches.</p>}
        </div>
      </Field>
      <Field label="Inputs" hint="Typed parameters the skill expects (shown to the agent as what to ask for).">
        <div className="mt-1 space-y-1.5">
          {d.inputs.map((inp, i) => (
            <div key={i} className="grid grid-cols-[1fr_90px_2fr_auto_auto] items-center gap-1.5">
              <Input value={inp.name} placeholder="name" onChange={(e) => set("inputs", d.inputs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} className="h-7 text-xs" />
              <select value={inp.type} onChange={(e) => set("inputs", d.inputs.map((x, j) => (j === i ? { ...x, type: e.target.value as SkillInputDef["type"] } : x)))} className="h-7 rounded-md border border-border bg-background px-1 text-xs">
                {["string", "number", "integer", "boolean", "date", "list"].map((t) => <option key={t}>{t}</option>)}
              </select>
              <Input value={inp.description ?? ""} placeholder="description" onChange={(e) => set("inputs", d.inputs.map((x, j) => (j === i ? { ...x, description: e.target.value } : x)))} className="h-7 text-xs" />
              <label className="flex items-center gap-1 text-[11px]"><input type="checkbox" checked={!!inp.required} onChange={(e) => set("inputs", d.inputs.map((x, j) => (j === i ? { ...x, required: e.target.checked } : x)))} />required</label>
              <button type="button" aria-label="Remove input" onClick={() => set("inputs", d.inputs.filter((_, j) => j !== i))} className="text-muted-foreground hover:text-destructive"><X className="h-3.5 w-3.5" /></button>
            </div>
          ))}
          <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => set("inputs", [...d.inputs, { name: "", type: "string", description: "", required: false }])}>
            <Plus className="mr-1 h-3 w-3" />Add input
          </Button>
        </div>
      </Field>
      {editing && editing.status !== "draft" && (
        <Field label="What changed (optional)"><Input value={d.changelog} onChange={(e) => set("changelog", e.target.value)} className="mt-1 h-8 text-xs" /></Field>
      )}
      {(errors.length > 0 || serverError) && (
        <ul className="space-y-0.5 rounded border border-destructive/40 bg-destructive/5 p-2 text-[11px] text-destructive" role="alert">
          {errors.map((e) => <li key={e}>{e}</li>)}
          {serverError && <li>{serverError}</li>}
        </ul>
      )}
      <div className="flex gap-2">
        <Button size="sm" className="text-xs" disabled={saving || errors.length > 0} onClick={() => void save()}>
          {saving && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}{editing ? "Save changes" : "Create skill"}
        </Button>
        <Button size="sm" variant="ghost" className="text-xs" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  )
}

// ── Import ───────────────────────────────────────────────────────────────────

function ImportPanel({ meta, onCancel, onImported }: { meta: SkillsMeta; onCancel: () => void; onImported: (s: OKFSkill) => void }) {
  const [markdown, setMarkdown] = useState("")
  const [preview, setPreview] = useState<SkillImportPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [scope, setScope] = useState<"user" | "tenant">("user")
  const fileRef = useRef<HTMLInputElement>(null)

  const run = async (text: string) => {
    setBusy(true)
    setError(null)
    try {
      setPreview(await previewSkillImport(text))
    } catch (err) {
      setPreview(null)
      setError(err instanceof Error ? err.message : "Could not check the file")
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (file: File | undefined) => {
    if (!file) return
    if (file.size > MAX_IMPORT_BYTES) {
      setPreview(null)
      setError(`That file is ${Math.round(file.size / 1000)} KB. Skill files are limited to ${MAX_IMPORT_BYTES / 1000} KB.`)
      return
    }
    const text = await file.text()
    setMarkdown(text)
    await run(text)
  }

  const create = async () => {
    setBusy(true)
    setError(null)
    try {
      onImported(await importSkill(markdown, scope))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <h3 className="text-sm font-semibold">Import a skill (.md)</h3>
      <p className="text-[11px] text-muted-foreground">A SKILL.md file with a frontmatter block. It is checked first, then saved as a draft. Nothing is active until it is activated.</p>
      <input ref={fileRef} type="file" accept=".md,text/markdown,text/plain" className="hidden" onChange={(e) => void onFile(e.target.files?.[0])} />
      <div className="flex gap-2">
        <Button size="sm" variant="outline" className="text-xs" onClick={() => fileRef.current?.click()}><Upload className="mr-1 h-3.5 w-3.5" />Choose file</Button>
        {meta.caller.admin && (
          <select value={scope} onChange={(e) => setScope(e.target.value as "user" | "tenant")} className="h-8 rounded-md border border-border bg-background px-2 text-xs" aria-label="Import into">
            <option value="user">Import as my private draft</option>
            <option value="tenant">Import as an organisation draft</option>
          </select>
        )}
        <Button size="sm" variant="ghost" className="text-xs" onClick={onCancel}>Cancel</Button>
      </div>
      {busy && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
      {error && <p className="text-[11px] text-destructive" role="alert">{error}</p>}
      {preview && (
        <div className="space-y-2 text-xs">
          {preview.errors.length > 0 && (
            <ul className="space-y-0.5 rounded border border-destructive/40 bg-destructive/5 p-2 text-[11px] text-destructive" role="alert">
              {preview.errors.map((e) => <li key={e}>{e}</li>)}
            </ul>
          )}
          {preview.warnings.length > 0 && (
            <ul className="space-y-0.5 rounded border border-amber-500/40 bg-amber-500/5 p-2 text-[11px] text-amber-500">
              {preview.warnings.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
          {preview.skill && (
            <div className="rounded border border-border p-2">
              <div className="font-semibold">{String(preview.skill.skill_name ?? "(no name)")}</div>
              <div className="text-muted-foreground">{String(preview.skill.description ?? "")}</div>
              <div className="mt-1 text-[10px] text-muted-foreground">Tools: {(preview.skill.tools_required ?? []).join(", ") || "none"}</div>
            </div>
          )}
          <Button size="sm" className="text-xs" disabled={!preview.ok || busy} onClick={() => void create()}>Create as draft</Button>
        </div>
      )}
    </div>
  )
}

// ── Detail drawer ────────────────────────────────────────────────────────────

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return <div className="rounded border border-border px-2 py-1"><div className="text-[10px] text-muted-foreground">{label}</div><div className="text-xs font-medium">{value}</div></div>
}

function SkillDrawer({ skill, meta, agents, onClose, onChanged, onEdit, notify }: {
  skill: OKFSkill
  meta: SkillsMeta
  agents: Array<{ agent_type: string; name?: string | null }>
  onClose: () => void
  onChanged: () => Promise<void>
  onEdit: (s: OKFSkill) => void
  notify: (m: string) => void
}) {
  const [versions, setVersions] = useState<SkillVersionRow[]>([])
  const [transferTo, setTransferTo] = useState("")
  const [busy, setBusy] = useState(false)
  const platform = skill.scope === "platform"

  useEffect(() => {
    let live = true
    getSkillVersions(skill.id).then((v) => { if (live) setVersions(v) }).catch(() => { if (live) setVersions([]) })
    return () => { live = false }
  }, [skill.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  const act = async (label: string, fn: () => Promise<unknown>, close = false) => {
    setBusy(true)
    try {
      await fn()
      notify(label)
      await onChanged()
      if (close) onClose()
    } catch (err) {
      notify(err instanceof Error ? err.message : "That did not work")
    } finally {
      setBusy(false)
    }
  }

  const download = async () => {
    try {
      const { filename, markdown } = await exportSkill(skill.id)
      const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }))
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      notify(err instanceof Error ? err.message : "Export failed")
    }
  }

  const tools = new Map(meta.tools.map((t) => [t.name, t]))
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <aside role="dialog" aria-label={`Skill ${skill.skill_name}`} className="h-full w-full max-w-xl overflow-y-auto border-l border-border bg-background p-4 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-2">
          <div>
            <h3 className="text-base font-semibold">{skill.skill_name}</h3>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Badge variant="outline" className="text-[10px]">v{skill.version}</Badge>
              <Badge variant="outline" className="text-[10px]">{SCOPE_LABEL[skill.scope]}</Badge>
              <Badge variant="outline" className={`text-[10px] ${skill.status === "active" ? "border-emerald-500/30 text-emerald-500" : skill.status === "draft" ? "border-amber-500/40 text-amber-500" : "text-muted-foreground"}`}>{skill.status}</Badge>
              <Badge variant="outline" className={`text-[10px] ${SAFETY_STYLE[skill.safety_class]}`}>{SAFETY_LABEL[skill.safety_class]}</Badge>
            </div>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>

        <p className="mt-3 text-xs text-muted-foreground">{skill.description}</p>
        {platform && <p className="mt-2 flex items-center gap-1 text-[11px] text-muted-foreground"><Lock className="h-3 w-3" />Shipped with the product and read-only. Fork it to customise.</p>}
        {skill.forked_from_id && <p className="mt-2 text-[11px] text-muted-foreground">Forked from an earlier skill (v{skill.forked_from_version}).</p>}

        <div className="mt-3 flex flex-wrap gap-1.5">
          {skill.can_edit && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => onEdit(skill)}><Pencil className="mr-1 h-3 w-3" />Edit</Button>}
          {meta.caller.author && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void act("Forked as your private draft", () => forkSkill(skill.id, "user"), true)}><GitFork className="mr-1 h-3 w-3" />Fork</Button>}
          {meta.caller.admin && !platform && skill.scope !== "user" && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void act("Forked into the organisation library as a draft", () => forkSkill(skill.id, "tenant"), true)}><Copy className="mr-1 h-3 w-3" />Fork to organisation</Button>}
          {skill.scope === "user" && skill.can_edit && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void act(meta.caller.admin ? "Shared with your organisation" : "Submitted to your organisation as a draft for an admin", () => shareSkill(skill.id), true)}><Share2 className="mr-1 h-3 w-3" />{meta.caller.admin ? "Share to organisation" : "Submit to organisation"}</Button>}
          {skill.can_publish && skill.status !== "active" && <Button size="sm" className="h-7 text-xs" disabled={busy} onClick={() => void act("Skill activated", () => activateSkill(skill.id))}>Activate</Button>}
          {skill.can_publish && skill.status === "active" && <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void act("Skill deactivated", () => deprecateSkill(skill.id))}>Deactivate</Button>}
          <Button size="sm" variant="outline" className="h-7 text-xs" disabled={busy} onClick={() => void download()}><Download className="mr-1 h-3 w-3" />Export .md</Button>
        </div>

        {meta.caller.admin && !platform && skill.scope !== "user" && (
          <div className="mt-3 flex items-center gap-2 rounded bg-muted/40 p-2 text-xs">
            <span>Also give to agent:</span>
            <select value={transferTo} onChange={(e) => setTransferTo(e.target.value)} className="h-7 rounded-md border border-border bg-background px-2 text-xs">
              <option value="">Select agent</option>
              {agents.map((a) => <option key={a.agent_type} value={a.agent_type}>{a.name || a.agent_type}</option>)}
            </select>
            <Button size="sm" className="h-7 text-xs" disabled={!transferTo || busy} onClick={() => void act(`Skill given to ${transferTo}`, () => transferOKFSkill(skill.id, transferTo))}>Transfer</Button>
          </div>
        )}

        <h4 className="mt-4 text-xs font-semibold">Instructions</h4>
        <div className="mt-1 rounded border border-border p-3"><SafeMarkdown text={skill.instructions || skill.guidance_prompt} /></div>

        <h4 className="mt-4 text-xs font-semibold">Tools</h4>
        <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
          {skill.tools_required.length === 0 && skill.tools_optional.length === 0 && <span className="text-muted-foreground">No tools needed.</span>}
          {skill.tools_required.map((t) => <span key={t} className="rounded border border-border px-1.5 py-0.5 font-mono" title={tools.get(t)?.mutates ? "changes data" : "reads"}>{t}{tools.get(t)?.requires_approval ? " (approval)" : ""}</span>)}
          {skill.tools_optional.map((t) => <span key={t} className="rounded border border-dashed border-border px-1.5 py-0.5 font-mono text-muted-foreground" title="used only if the agent has it">{t} (optional)</span>)}
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">Skills cannot grant tools. A required tool the agent does not have makes the skill skip.</p>

        {skill.inputs.length > 0 && (
          <>
            <h4 className="mt-4 text-xs font-semibold">Inputs</h4>
            <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
              {skill.inputs.map((i) => <li key={i.name}><span className="font-mono text-foreground">{i.name}</span> ({i.type}{i.required ? ", required" : ""}) {i.description}</li>)}
            </ul>
          </>
        )}
        {skill.triggers.length > 0 && (
          <>
            <h4 className="mt-4 text-xs font-semibold">Triggers</h4>
            <p className="mt-1 text-[11px] text-muted-foreground">{skill.triggers.join(" · ")}</p>
          </>
        )}
        {skill.examples.length > 0 && (
          <>
            <h4 className="mt-4 text-xs font-semibold">Examples</h4>
            {skill.examples.map((e, i) => <div key={i} className="mt-1 rounded border border-border p-2 text-[11px]"><div className="font-medium">{e.title}</div><div className="text-muted-foreground">Ask: {e.input}</div><div className="text-muted-foreground">Result: {e.output}</div></div>)}
          </>
        )}

        <h4 className="mt-4 text-xs font-semibold">Use</h4>
        <div className="mt-1 grid grid-cols-3 gap-2">
          <Stat label="Times applied" value={skill.usage_count} />
          <Stat label="Last used" value={when(skill.last_used_at)} />
          <Stat label="Feedback" value={<span className="flex items-center gap-2"><ThumbsUp className="h-3 w-3" />{skill.helpful_count}<ThumbsDown className="h-3 w-3" />{skill.unhelpful_count}</span>} />
        </div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
          Was this skill useful?
          <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" disabled={busy} onClick={() => void act("Thanks, noted", () => sendSkillFeedback(skill.id, true))}><ThumbsUp className="h-3 w-3" /></Button>
          <Button size="sm" variant="outline" className="h-6 px-2 text-[11px]" disabled={busy} onClick={() => void act("Thanks, noted", () => sendSkillFeedback(skill.id, false))}><ThumbsDown className="h-3 w-3" /></Button>
        </div>

        <h4 className="mt-4 text-xs font-semibold">Version history</h4>
        <ul className="mt-1 space-y-1 text-[11px]">
          {versions.length === 0 && <li className="text-muted-foreground">No history yet.</li>}
          {versions.map((v) => <li key={v.id} className="flex justify-between gap-2 rounded border border-border px-2 py-1"><span>v{v.version} <span className="text-muted-foreground">{v.status}</span> {v.changelog && <span className="text-muted-foreground">- {v.changelog}</span>}</span><span className="text-muted-foreground">{when(v.created_at)}</span></li>)}
        </ul>
      </aside>
    </div>
  )
}

// ── Panel ────────────────────────────────────────────────────────────────────

export function OKFSkillsView() {
  const [skills, setSkills] = useState<OKFSkill[]>([])
  const [meta, setMeta] = useState<SkillsMeta | null>(null)
  const [agents, setAgents] = useState<Array<{ agent_type: string; name?: string | null }>>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>("platform")
  const [query, setQuery] = useState("")
  const [agentFilter, setAgentFilter] = useState("")
  const [categoryFilter, setCategoryFilter] = useState("")
  const [safetyFilter, setSafetyFilter] = useState("")
  const [statusFilter, setStatusFilter] = useState("")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mode, setMode] = useState<"none" | "create" | "edit" | "import">("none")
  const [editing, setEditing] = useState<OKFSkill | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [items, m, ag] = await Promise.all([listSkills({ status: "all" }), getSkillsMeta(), listAgents().catch(() => [])])
      setSkills(items)
      setMeta(m)
      setAgents(ag.map(({ agent_type, name }) => ({ agent_type, name })))
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Could not load skills")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const inTab = useCallback((s: OKFSkill, t: Tab) =>
    t === "platform" ? s.scope === "platform" : t === "mine" ? s.scope === "user" : s.scope === "tenant" || s.scope === "team", [])
  const counts = useMemo(() => ({
    platform: skills.filter((s) => inTab(s, "platform")).length,
    organisation: skills.filter((s) => inTab(s, "organisation")).length,
    mine: skills.filter((s) => inTab(s, "mine")).length,
  }), [skills, inTab])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return skills.filter((s) => {
      if (!inTab(s, tab)) return false
      if (agentFilter && s.target_agent_types.length && !s.target_agent_types.includes(agentFilter)) return false
      if (categoryFilter && s.category !== categoryFilter) return false
      if (safetyFilter && s.safety_class !== safetyFilter) return false
      if (statusFilter && s.status !== statusFilter) return false
      if (q && !`${s.skill_name} ${s.description} ${s.tags.join(" ")} ${s.triggers.join(" ")}`.toLowerCase().includes(q)) return false
      return true
    })
  }, [skills, tab, query, agentFilter, categoryFilter, safetyFilter, statusFilter, inTab])

  const selected = skills.find((s) => s.id === selectedId) ?? null
  const categories = useMemo(() => Array.from(new Set(skills.map((s) => s.category))).sort(), [skills])

  const afterSave = async (s: OKFSkill, note: string) => {
    setMode("none")
    setEditing(null)
    setMsg(note)
    await load()
    setTab(s.scope === "platform" ? "platform" : s.scope === "user" ? "mine" : "organisation")
    setSelectedId(s.id)
  }

  const drafts = skills.filter((s) => s.status === "draft" && s.scope !== "user").length

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">Skills</h2>
          <p className="max-w-2xl text-xs text-muted-foreground">
            Reusable procedures agents follow when a request fits. The few most relevant skills are added to an agent&apos;s prompt for that turn.
            Skills guide how to work; they never add tools or skip approvals.
          </p>
        </div>
        {meta && (
          <div className="flex gap-2">
            {meta.caller.author && <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => { setMode("import"); setEditing(null) }}><Upload className="h-3.5 w-3.5" />Import .md</Button>}
            {meta.caller.author && <Button size="sm" className="gap-1 text-xs" onClick={() => { setMode("create"); setEditing(null) }}><Plus className="h-3.5 w-3.5" />New skill</Button>}
          </div>
        )}
      </div>

      {msg && (
        <div className="flex items-center justify-between rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs text-primary" role="status">
          <span>{msg}</span>
          <button type="button" aria-label="Dismiss" onClick={() => setMsg(null)} className="text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
        </div>
      )}

      {meta && mode === "create" && <SkillEditor meta={meta} initial={EMPTY} editing={null} onCancel={() => setMode("none")} onSaved={(s, n) => void afterSave(s, n)} />}
      {meta && mode === "edit" && editing && <SkillEditor meta={meta} initial={fromSkill(editing)} editing={editing} onCancel={() => { setMode("none"); setEditing(null) }} onSaved={(s, n) => void afterSave(s, n)} />}
      {meta && mode === "import" && <ImportPanel meta={meta} onCancel={() => setMode("none")} onImported={(s) => void afterSave(s, "Imported as a draft. Review it, then activate it.")} />}

      <div className="flex flex-wrap gap-1 border-b border-border" role="tablist">
        {([["platform", "Platform library"], ["organisation", "My organisation"], ["mine", "Mine"]] as const).map(([key, label]) => (
          <button key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
            className={`-mb-px border-b-2 px-3 py-1.5 text-xs font-medium ${tab === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
            {label} <span className="text-muted-foreground">({counts[key]})</span>
          </button>
        ))}
      </div>
      {tab === "organisation" && drafts > 0 && meta?.caller.admin && (
        <p className="flex items-center gap-1 text-[11px] text-amber-500"><AlertTriangle className="h-3 w-3" />{drafts} draft{drafts === 1 ? "" : "s"} waiting for an admin to activate.</p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-2 h-3.5 w-3.5 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search skills" aria-label="Search skills" className="h-8 w-56 pl-7 text-xs" />
        </div>
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} aria-label="Agent" className="h-8 rounded-md border border-border bg-background px-2 text-xs">
          <option value="">All agents</option>
          {(meta?.agent_types ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} aria-label="Category" className="h-8 rounded-md border border-border bg-background px-2 text-xs">
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={safetyFilter} onChange={(e) => setSafetyFilter(e.target.value)} aria-label="Safety" className="h-8 rounded-md border border-border bg-background px-2 text-xs">
          <option value="">Any safety class</option>
          {(["read_only", "drafts_only", "can_act"] as const).map((c) => <option key={c} value={c}>{SAFETY_LABEL[c]}</option>)}
        </select>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Status" className="h-8 rounded-md border border-border bg-background px-2 text-xs">
          <option value="">Any status</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="deprecated">Deactivated</option>
        </select>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-10"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
      ) : loadError ? (
        <div className="rounded-lg border border-destructive/40 p-4 text-xs text-destructive" role="alert">
          {loadError} <Button size="sm" variant="outline" onClick={() => void load()} className="ml-2">Retry</Button>
        </div>
      ) : shown.length === 0 ? (
        <EmptyState tab={tab} filtered={skills.some((s) => inTab(s, tab))} canCreate={!!meta?.caller.author} />
      ) : (
        <div className="divide-y divide-border rounded-lg border border-border">
          {shown.map((s) => (
            <button key={s.id} type="button" onClick={() => setSelectedId(s.id)} className="block w-full space-y-1 p-3 text-left text-xs hover:bg-muted/20">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-foreground">{s.skill_name}</span>
                <Badge variant="outline" className="text-[10px]">v{s.version}</Badge>
                <Badge variant="outline" className={`text-[10px] ${s.status === "active" ? "border-emerald-500/30 text-emerald-500" : s.status === "draft" ? "border-amber-500/40 text-amber-500" : "text-muted-foreground"}`}>{s.status === "deprecated" ? "deactivated" : s.status}</Badge>
                <Badge variant="outline" className={`text-[10px] ${SAFETY_STYLE[s.safety_class]}`}>{SAFETY_LABEL[s.safety_class]}</Badge>
                {s.forked_from_id && <Badge variant="outline" className="text-[10px]">fork</Badge>}
              </div>
              <p className="text-muted-foreground">{s.description}</p>
              <p className="text-[10px] text-muted-foreground">
                {s.category} · {s.target_agent_types.length ? s.target_agent_types.join(", ") : "all agents"} · {s.tools_required.length} tool{s.tools_required.length === 1 ? "" : "s"} · applied {s.usage_count} time{s.usage_count === 1 ? "" : "s"}
              </p>
            </button>
          ))}
        </div>
      )}

      {selected && meta && (
        <SkillDrawer skill={selected} meta={meta} agents={agents} onClose={() => setSelectedId(null)} onChanged={load}
          onEdit={(s) => { setEditing(s); setMode("edit"); setSelectedId(null) }} notify={setMsg} />
      )}
    </div>
  )
}

function EmptyState({ tab, filtered, canCreate }: { tab: Tab; filtered: boolean; canCreate: boolean }) {
  if (filtered) return <p className="rounded-lg border py-6 text-center text-xs text-muted-foreground">No skills match these filters.</p>
  const text =
    tab === "platform"
      ? "The platform library is empty on this server. It is loaded when the memory service starts; if you expected skills here, check that service's logs for the skills migration."
      : tab === "organisation"
        ? `Your organisation has no skills yet. Fork one from the platform library to adapt it${canCreate ? ", or create your own" : ""}.`
        : `You have no private skills yet.${canCreate ? " Create one, import a .md file, or fork a library skill." : " Ask an analyst or admin to create skills."}`
  return <p className="rounded-lg border px-4 py-6 text-center text-xs text-muted-foreground">{text}</p>
}
