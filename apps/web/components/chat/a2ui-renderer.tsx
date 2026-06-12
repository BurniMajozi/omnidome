"use client"

import type React from "react"

import { useState, useCallback } from "react"
import {
  CheckCircle2,
  AlertCircle,
  Shield,
  Code2,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import {
  validateA2UI,
  type A2UIPayload,
  type A2UIComponent,
  type A2UIValidationResult,
} from "@/lib/orchestrator-api"

// ── Safe component renderers ─────────────────────────────────────────────

const SAFE_COMPONENTS = new Set([
  "Badge", "Button", "Card", "CheckBox", "Column", "DateTimeInput",
  "Divider", "Form", "Input", "List", "Row", "Select", "Table",
  "Tabs", "Text", "TextArea",
])

interface RendererProps {
  components: A2UIComponent[]
  data?: Record<string, unknown>
}

/**
 * Renders a validated A2UI component tree.
 * Only whitelisted components are rendered — anything else is blocked.
 */
export function A2UIRenderer({ components, data = {} }: RendererProps) {
  const componentMap = new Map(components.map((c) => [c.id, c]))

  const root = components[0]?.id
  if (!root) return null

  return (
    <div className="a2ui-surface space-y-2">
      {renderComponent(root, componentMap, data)}
    </div>
  )
}

function renderComponent(
  id: string,
  componentMap: Map<string, A2UIComponent>,
  data: Record<string, unknown>,
): React.ReactNode {
  const comp = componentMap.get(id)
  if (!comp) return null

  const name = Object.keys(comp.component)[0]
  const props = comp.component[name] as Record<string, unknown>

  if (!SAFE_COMPONENTS.has(name)) {
    return (
      <div className="rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-400">
        Blocked: {name} is not in the safe component allow-list
      </div>
    )
  }

  switch (name) {
    case "Text":
      return (
        <p className={cn("text-sm text-foreground", props.className as string)}>
          {resolveValue(props.text as string, data)}
        </p>
      )

    case "Badge":
      return (
        <Badge variant={props.variant as "default" | "secondary" | "destructive" | "outline"}>
          {resolveValue(props.text as string, data)}
        </Badge>
      )

    case "Button":
      return (
        <Button
          variant={props.variant as "default" | "secondary" | "destructive" | "outline" | "ghost"}
          size={props.size as "default" | "sm" | "lg" | "icon"}
          disabled={props.disabled as boolean}
          className={props.className as string}
        >
          {resolveValue(props.label as string, data)}
        </Button>
      )

    case "Card":
      return (
        <div className="rounded-lg border border-border bg-card p-4">
          {props.title && (
            <h4 className="text-sm font-semibold text-foreground mb-2">
              {resolveValue(props.title as string, data)}
            </h4>
          )}
          {(props.children as string[])?.map((childId) => (
            <div key={childId}>{renderComponent(childId, componentMap, data)}</div>
          ))}
        </div>
      )

    case "Input":
      return (
        <Input
          placeholder={props.placeholder as string}
          defaultValue={resolveValue(props.value as string, data)}
          disabled={props.disabled as boolean}
          type={props.type as string}
          className={props.className as string}
        />
      )

    case "TextArea":
      return (
        <Textarea
          placeholder={props.placeholder as string}
          defaultValue={resolveValue(props.value as string, data)}
          disabled={props.disabled as boolean}
          rows={props.rows as number}
          className={props.className as string}
        />
      )

    case "List":
      return (
        <ul className="space-y-1">
          {(props.items as string[])?.map((itemId) => (
            <li key={itemId} className="text-sm text-foreground">
              {renderComponent(itemId, componentMap, data)}
            </li>
          ))}
        </ul>
      )

    case "Table":
      return (
        <div className="overflow-x-auto rounded border border-border">
          <table className="w-full text-sm">
            {props.headers && (
              <thead>
                <tr className="border-b border-border bg-secondary">
                  {(props.headers as string[]).map((h) => (
                    <th key={h} className="px-3 py-2 text-left font-medium text-foreground">{h}</th>
                  ))}
                </tr>
              </thead>
            )}
            <tbody>
              {(props.rows as string[])?.map((rowId) => (
                <tr key={rowId} className="border-b border-border">
                  {renderComponent(rowId, componentMap, data)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )

    case "Row":
      return (
        <div className="flex gap-2">
          {(props.children as string[])?.map((childId) => (
            <div key={childId}>{renderComponent(childId, componentMap, data)}</div>
          ))}
        </div>
      )

    case "Column":
      return (
        <div className="flex flex-col gap-2">
          {(props.children as string[])?.map((childId) => (
            <div key={childId}>{renderComponent(childId, componentMap, data)}</div>
          ))}
        </div>
      )

    case "Tabs":
      return (
        <div className="space-y-2">
          {(props.tabs as Array<{ id: string; label: string }>)?.map((tab) => (
            <div key={tab.id} className="rounded border border-border p-3">
              <p className="text-xs font-medium text-muted-foreground mb-1">{tab.label}</p>
              {renderComponent(tab.id, componentMap, data)}
            </div>
          ))}
        </div>
      )

    case "Form":
      return (
        <form className="space-y-3" onSubmit={(e) => e.preventDefault()}>
          {(props.children as string[])?.map((childId) => (
            <div key={childId}>{renderComponent(childId, componentMap, data)}</div>
          ))}
        </form>
      )

    case "Select":
      return (
        <select
          className="w-full rounded border border-border bg-card px-3 py-2 text-sm text-foreground"
          defaultValue={resolveValue(props.value as string, data)}
        >
          {(props.options as Array<{ value: string; label: string }>)?.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )

    case "CheckBox":
      return (
        <label className="flex items-center gap-2 text-sm text-foreground">
          <input
            type="checkbox"
            defaultChecked={props.checked as boolean}
            className="rounded border-border"
          />
          {resolveValue(props.label as string, data)}
        </label>
      )

    case "DateTimeInput":
      return (
        <Input
          type="datetime-local"
          defaultValue={resolveValue(props.value as string, data)}
          className={props.className as string}
        />
      )

    case "Divider":
      return <hr className="border-border" />

    default:
      return null
  }
}

/**
 * Resolves template values like "{{customer.name}}" from data context.
 */
function resolveValue(template: string, data: Record<string, unknown>): string {
  if (!template) return ""
  return template.replace(/\{\{([^}]+)\}\}/g, (_, path) => {
    const parts = path.trim().split(".")
    let value: unknown = data
    for (const part of parts) {
      if (value && typeof value === "object") {
        value = (value as Record<string, unknown>)[part]
      } else {
        return ""
      }
    }
    return String(value ?? "")
  })
}

// ── A2UI Validator Panel ─────────────────────────────────────────────────

interface A2UIPanelProps {
  payload: A2UIPayload
  onValidationResult?: (result: A2UIValidationResult | null) => void
}

export function A2UIValidatorPanel({ payload, onValidationResult }: A2UIPanelProps) {
  const [result, setResult] = useState<A2UIValidationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isValidating, setIsValidating] = useState(false)

  const handleValidate = useCallback(async () => {
    setIsValidating(true)
    setError(null)
    try {
      const res = await validateA2UI(payload)
      setResult(res)
      onValidationResult?.(res)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation failed")
      setResult(null)
      onValidationResult?.(null)
    } finally {
      setIsValidating(false)
    }
  }, [payload, onValidationResult])

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Shield className="h-4 w-4 text-primary" />
        <span className="text-sm font-medium text-foreground">A2UI Validation</span>
        <Button
          size="sm"
          variant="outline"
          onClick={handleValidate}
          disabled={isValidating}
        >
          {isValidating ? "Validating..." : "Validate"}
        </Button>
      </div>

      {result && (
        <div className="flex items-center gap-2 rounded border border-emerald-500/30 bg-emerald-500/10 px-3 py-2">
          <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          <span className="text-xs text-emerald-400">
            Valid — {result.components} component(s) on surface "{result.surface_id}"
          </span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2">
          <AlertCircle className="h-4 w-4 text-red-400" />
          <span className="text-xs text-red-400">{error}</span>
        </div>
      )}

      <div className="rounded border border-border bg-background/50 p-3">
        <div className="flex items-center gap-2 mb-2">
          <Code2 className="h-3 w-3 text-muted-foreground" />
          <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            Component Tree
          </span>
        </div>
        <div className="space-y-1">
          {payload.components.map((comp) => {
            const compName = Object.keys(comp.component)[0]
            const isSafe = SAFE_COMPONENTS.has(compName)
            return (
              <div
                key={comp.id}
                className="flex items-center gap-2 text-xs"
              >
                <div className={cn(
                  "h-1.5 w-1.5 rounded-full",
                  isSafe ? "bg-emerald-400" : "bg-red-400",
                )} />
                <span className="font-mono text-foreground">{comp.id}</span>
                <span className="text-muted-foreground">→</span>
                <span className={cn(
                  "font-medium",
                  isSafe ? "text-foreground" : "text-red-400",
                )}>
                  {compName}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
