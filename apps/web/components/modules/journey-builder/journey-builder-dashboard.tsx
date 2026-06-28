"use client"

import { useEffect, useState, useCallback } from "react"
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, FunnelChart, Funnel, LabelList,
} from "recharts"
import {
  Plus, Trash2, Edit3, Play, Pause, Copy, ChevronDown, ChevronRight,
  ArrowRight, Zap, Target, DollarSign, Users, TrendingUp, AlertCircle,
  CheckCircle, XCircle, Settings, Eye, Save, X,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { journeyApi } from "@/lib/journey-api"
import type {
  Journey, JourneyRule, Offer, FunnelData, ROIEntry,
  AttributeDef, OperatorDef, OfferTypeDef,
} from "@/lib/journey-api"
import { supabase } from "@/lib/supabase/client"

const COLORS = ["#4ade80", "#60a5fa", "#a855f7", "#f97316", "#ef4444", "#14b8a6", "#eab308", "#ec4899"]

const FALLBACK_TENANT_ID = "00000000-0000-0000-0000-000000000001"

// ---------------------------------------------------------------------------
// Empty rule template
// ---------------------------------------------------------------------------
function emptyRule(group = 0): Partial<JourneyRule> {
  return {
    journey_id: "",
    rule_group: group,
    attribute: "none",
    operator: "none",
    value: { value: 70, type: "number" },
    is_active: true,
    sort_order: 0,
  }
}

function emptyOffer(): Partial<Offer> {
  return {
    name: "",
    description: "",
    offer_type: "percentage_discount",
    parameters: { percent: 10, duration_months: 3 },
    max_per_customer: 1,
  }
}

function emptyJourney(tenantId?: string): Partial<Journey> {
  return {
    name: "",
    description: "",
    trigger_event: "cancel_initiated",
    priority: 0,
    channel: "portal",
    status: "draft",
    ...(tenantId ? { tenant_id: tenantId } : {}),
  }
}

// ---------------------------------------------------------------------------
// RuleEditor — inline rule condition row
// ---------------------------------------------------------------------------
function RuleEditor({
  rule,
  onChange,
  onRemove,
  attributes,
  operators,
}: {
  rule: Partial<JourneyRule>
  onChange: (r: Partial<JourneyRule>) => void
  onRemove: () => void
  attributes: AttributeDef[]
  operators: OperatorDef[]
}) {
  const selectedAttr = attributes.find((a) => a.name === rule.attribute)
  const allowedOps = operators.filter((o) =>
    selectedAttr ? o.types.includes(selectedAttr.type) : true
  )

  const renderValueInput = () => {
    const v = rule.value || {}
    switch (rule.operator) {
      case "between":
        return (
          <div className="flex gap-1 items-center">
            <Input
              type="number"
              className="h-7 w-16 px-1 text-xs"
              value={v.min ?? ""}
              onChange={(e) => onChange({ ...rule, value: { ...v, min: Number(e.target.value) } })}
              placeholder="Min"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <Input
              type="number"
              className="h-7 w-16 px-1 text-xs"
              value={v.max ?? ""}
              onChange={(e) => onChange({ ...rule, value: { ...v, max: Number(e.target.value) } })}
              placeholder="Max"
            />
          </div>
        )
      case "in":
      case "not_in":
        return (
          <Input
            className="h-7 px-2 text-xs w-32"
            value={Array.isArray(v.values) ? v.values.join(", ") : ""}
            onChange={(e) =>
              onChange({ ...rule, value: { ...v, values: e.target.value.split(",").map((s) => s.trim()) } })
            }
            placeholder="val1, val2, ..."
          />
        )
      default:
        return (
          <Input
            type={selectedAttr?.type === "number" ? "number" : "text"}
            className="h-7 px-2 text-xs w-24"
            value={v.value ?? ""}
            onChange={(e) => {
              const val = selectedAttr?.type === "number" ? Number(e.target.value) : e.target.value
              onChange({ ...rule, value: { ...v, value: val } })
            }}
            placeholder="Value"
          />
        )
    }
  }

  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/30 p-2">
      <Select
        value={rule.attribute || "none"}
        onValueChange={(val) => onChange({ ...rule, attribute: val === "none" ? "" : val, value: { value: "", type: "string" } })}
      >
        <SelectTrigger className="h-7 w-32 text-xs">
          <SelectValue placeholder="Select attribute..." />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">Select attribute...</SelectItem>
          {attributes.length > 0 ? (
            attributes.map((a) => (
              <SelectItem key={a.name} value={a.name} className="text-xs">
                {a.name}
              </SelectItem>
            ))
          ) : (
            <SelectItem value="loading-attributes" disabled className="text-xs">
              No attributes loaded
            </SelectItem>
          )}
        </SelectContent>
      </Select>

      <Select
        value={rule.operator || "none"}
        onValueChange={(val) => onChange({ ...rule, operator: val === "none" ? "" : val })}
      >
        <SelectTrigger className="h-7 w-24 text-xs">
          <SelectValue placeholder="Select op..." />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="none">Select op...</SelectItem>
          {allowedOps.length > 0 ? (
            allowedOps.map((o) => (
              <SelectItem key={o.op} value={o.op} className="text-xs">
                {o.label}
              </SelectItem>
            ))
          ) : (
            <SelectItem value="loading-operators" disabled className="text-xs">
              No operators loaded
            </SelectItem>
          )}
        </SelectContent>
      </Select>

      {renderValueInput()}

      <Switch
        checked={rule.is_active}
        onCheckedChange={(checked) => onChange({ ...rule, is_active: checked })}
        className="scale-75"
      />

      <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onRemove}>
        <Trash2 className="h-3 w-3 text-red-400" />
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// OfferConfig — offer type-specific parameter form
// ---------------------------------------------------------------------------
function OfferConfig({
  offer,
  onChange,
  offerTypes,
}: {
  offer: Partial<Offer>
  onChange: (o: Partial<Offer>) => void
  offerTypes: OfferTypeDef[]
}) {
  const selectedType = offerTypes.find((t) => t.type === offer.offer_type)
  const params = offer.parameters || {}

  const updateParam = (key: string, value: any) => {
    onChange({ ...offer, parameters: { ...params, [key]: value } })
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Name</Label>
          <Input
            className="h-8 text-sm"
            value={offer.name || ""}
            onChange={(e) => onChange({ ...offer, name: e.target.value })}
            placeholder="e.g. 15% Loyalty Discount"
          />
        </div>
        <div>
          <Label className="text-xs">Type</Label>
          <Select
            value={offer.offer_type}
            onValueChange={(val) => {
              const t = offerTypes.find((ot) => ot.type === val)
              const defaultParams: Record<string, any> = {}
              if (t) {
                Object.entries(t.params).forEach(([k, type]) => {
                  defaultParams[k] = type === "number" ? 0 : ""
                })
              }
              onChange({ ...offer, offer_type: val, parameters: defaultParams })
            }}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {offerTypes.length > 0 ? (
                offerTypes.map((t) => (
                  <SelectItem key={t.type} value={t.type} className="text-xs">
                    {t.label}
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="loading-offer-types" disabled className="text-xs">
                  No offer types loaded
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div>
        <Label className="text-xs">Description</Label>
        <Input
          className="h-8 text-sm"
          value={offer.description || ""}
          onChange={(e) => onChange({ ...offer, description: e.target.value })}
          placeholder="Shown to retention team only"
        />
      </div>

      {/* Type-specific params */}
      {selectedType && (
        <div className="space-y-2 rounded-lg border border-border bg-secondary/20 p-3">
          <p className="text-xs font-medium text-foreground">Offer Parameters</p>
          {Object.entries(selectedType.params).map(([key, type]) => (
            <div key={key} className="flex items-center justify-between">
              <Label className="text-xs text-muted-foreground">{key.replace(/_/g, " ")}</Label>
              <Input
                type={type === "number" ? "number" : "text"}
                className="h-7 w-28 text-xs px-2"
                value={params[key] ?? ""}
                onChange={(e) =>
                  updateParam(key, type === "number" ? Number(e.target.value) : e.target.value)
                }
              />
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Max per customer</Label>
          <Input
            type="number"
            className="h-8 text-sm"
            value={offer.max_per_customer || 1}
            onChange={(e) => onChange({ ...offer, max_per_customer: Number(e.target.value) })}
          />
        </div>
        <div>
          <Label className="text-xs">Max total uses (empty = unlimited)</Label>
          <Input
            type="number"
            className="h-8 text-sm"
            value={offer.max_total_redemptions ?? ""}
            onChange={(e) =>
              onChange({
                ...offer,
                max_total_redemptions: e.target.value ? Number(e.target.value) : undefined,
              })
            }
          />
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Journey Builder — full journey creation/editing
// ---------------------------------------------------------------------------
function JourneyBuilder({
  journey,
  offers,
  attributes,
  operators,
  offerTypes,
  onSave,
  onCancel,
}: {
  journey: Partial<Journey>
  offers: Offer[]
  attributes: AttributeDef[]
  operators: OperatorDef[]
  offerTypes: OfferTypeDef[]
  onSave: (j: Partial<Journey>, rules: Partial<JourneyRule>[]) => void
  onCancel: () => void
}) {
  const [form, setForm] = useState<Partial<Journey>>(journey)
  const [rules, setRules] = useState<Partial<JourneyRule>[]>([emptyRule(0)])

  const updateRule = (index: number, r: Partial<JourneyRule>) => {
    setRules((prev) => prev.map((rule, i) => (i === index ? { ...rule, ...r } : rule)))
  }

  const removeRule = (index: number) => {
    setRules((prev) => prev.filter((_, i) => i !== index))
  }

  const addRule = (group: number) => {
    setRules((prev) => [...prev, { ...emptyRule(group), sort_order: prev.length }])
  }

  // Group rules
  const groups: Record<number, { rules: Partial<JourneyRule>[]; indices: number[] }> = {}
  rules.forEach((r, i) => {
    const g = r.rule_group || 0
    if (!groups[g]) groups[g] = { rules: [], indices: [] }
    groups[g].rules.push(r)
    groups[g].indices.push(i)
  })

  return (
    <div className="space-y-4">
      {/* Basic Info */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Journey Name</Label>
          <Input
            className="h-8 text-sm"
            value={form.name || ""}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="e.g. High-Risk Premium Save"
          />
        </div>
        <div>
          <Label className="text-xs">Priority (higher = first)</Label>
          <Input
            type="number"
            className="h-8 text-sm"
            value={form.priority || 0}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
          />
        </div>
      </div>

      <div>
        <Label className="text-xs">Description</Label>
        <Input
          className="h-8 text-sm"
          value={form.description || ""}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      </div>

      {/* Channel */}
      <div>
        <Label className="text-xs">Channel</Label>
        <Select
          value={form.channel || "portal"}
          onValueChange={(val) => setForm({ ...form, channel: val })}
        >
          <SelectTrigger className="h-8 text-sm w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="portal">Customer Portal</SelectItem>
            <SelectItem value="email">Email</SelectItem>
            <SelectItem value="sms">SMS</SelectItem>
            <SelectItem value="phone">Phone Call</SelectItem>
            <SelectItem value="agent">Agent-initiated</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Offer Selection */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs">Primary Offer</Label>
          <Select
            value={form.offer_id || "none"}
            onValueChange={(val) => setForm({ ...form, offer_id: val === "none" ? "" : val })}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder="Select offer..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">Select offer...</SelectItem>
              {offers.length > 0 ? (
                offers.map((o) => (
                  <SelectItem key={o.id} value={o.id} className="text-xs">
                    {o.name} ({o.offer_type})
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="loading-offers" disabled className="text-xs">
                  No offers loaded
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs">Fallback Offer</Label>
          <Select
            value={form.fallback_offer_id || "none"}
            onValueChange={(val) => setForm({ ...form, fallback_offer_id: val === "none" ? "" : val })}
          >
            <SelectTrigger className="h-8 text-sm">
              <SelectValue placeholder="Optional fallback..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">None</SelectItem>
              {offers.length > 0 ? (
                offers.map((o) => (
                  <SelectItem key={o.id} value={o.id} className="text-xs">
                    {o.name} ({o.offer_type})
                  </SelectItem>
                ))
              ) : (
                <SelectItem value="loading-fallback-offers" disabled className="text-xs">
                  No offers loaded
                </SelectItem>
              )}
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Rule Groups */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <Label className="text-sm font-medium">
            Targeting Rules
            <span className="text-xs text-muted-foreground ml-2">
              All rules in a group = AND • Between groups = OR
            </span>
          </Label>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 text-xs gap-1"
            onClick={() => addRule(Object.keys(groups).length)}
          >
            <Plus className="h-3 w-3" /> Add Rule Group
          </Button>
        </div>

        <div className="space-y-4">
          {Object.entries(groups).map(([groupId, { rules: groupRules, indices }]) => (
            <div key={groupId} className="relative rounded-lg border border-border bg-secondary/20 p-3">
              {/* OR Connector indicator between groups */}
              {Number(groupId) > 0 && (
                <div className="absolute -top-3.5 left-6 rounded-md bg-amber-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-amber-500 border border-amber-500/30">
                  OR
                </div>
              )}
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold text-foreground">
                  Condition Group {Number(groupId) + 1}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-5 text-xs gap-1 hover:text-primary"
                  onClick={() => addRule(Number(groupId))}
                >
                  <Plus className="h-3 w-3" /> Add Condition (AND)
                </Button>
              </div>
              <div className="relative pl-4 border-l-2 border-primary/20 space-y-2">
                {groupRules.map((r, gi) => (
                  <div key={indices[gi]} className="relative">
                    {/* AND text between adjacent items in a group */}
                    {gi > 0 && (
                      <div className="absolute -top-1.5 -left-7 scale-90 rounded bg-primary/10 px-1 text-[9px] font-bold text-primary border border-primary/20">
                        AND
                      </div>
                    )}
                    <RuleEditor
                      rule={r}
                      onChange={(updated) => updateRule(indices[gi], updated)}
                      onRemove={() => removeRule(indices[gi])}
                      attributes={attributes}
                      operators={operators}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          className="bg-primary gap-1"
          onClick={() => onSave(form, rules)}
        >
          <Save className="h-3 w-3" /> Save Journey
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Dashboard Component
// ---------------------------------------------------------------------------
export function JourneyBuilderDashboard() {
  const [tenantId, setTenantId] = useState(FALLBACK_TENANT_ID)
  const [tab, setTab] = useState("journeys")
  const [journeys, setJourneys] = useState<Journey[]>([])
  const [offers, setOffers] = useState<Offer[]>([])
  const [funnel, setFunnel] = useState<FunnelData[]>([])
  const [roi, setRoi] = useState<ROIEntry[]>([])
  const [attributes, setAttributes] = useState<AttributeDef[]>([])
  const [operators, setOperators] = useState<OperatorDef[]>([])
  const [offerTypes, setOfferTypes] = useState<OfferTypeDef[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isOffline, setIsOffline] = useState(false)

  // Resolve tenant ID from Supabase session (falls back to dev default)
  useEffect(() => {
    const resolve = (session: Parameters<Parameters<typeof supabase.auth.onAuthStateChange>[0]>[1]) => {
      setTenantId(
        session?.user?.user_metadata?.tenant_id ??
        session?.user?.app_metadata?.tenant_id ??
        FALLBACK_TENANT_ID
      )
    }
    supabase.auth.getSession().then(({ data }) => resolve(data.session))
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => resolve(session))
    return () => listener.subscription.unsubscribe()
  }, [])

  const loadData = useCallback(async () => {
    const safe = <T,>(p: Promise<T>) => p.catch((): null => null)
    setLoading(true)
    setError(null)
    try {
      // Core endpoints — if these fail the service is down; set offline mode
      const [jData, oData, aData] = await Promise.all([
        journeyApi.listJourneys(tenantId),
        journeyApi.listOffers(tenantId),
        journeyApi.getAttributes(),
      ])
      setJourneys(jData.journeys || [])
      setOffers(oData.offers || [])
      setAttributes(aData.attributes || [])
      setOperators(aData.operators || [])
      setOfferTypes(aData.offer_types || [])
      setIsOffline(false)

      // Analytics endpoints — optional; failure doesn't block the journeys UI
      const [fData, rData] = await Promise.all([
        safe(journeyApi.getFunnel(tenantId)),
        safe(journeyApi.getROI(tenantId)),
      ])
      setFunnel(fData?.funnel ?? [])
      setRoi(rData?.roi ?? [])
    } catch (err: any) {
      console.error("Failed to load journey data:", err)
      setError("Retention journey service is currently unreachable. Operating in offline simulation mode.")
      setIsOffline(true)
      setJourneys([])
      setOffers([])
      setAttributes([])
      setOperators([])
      setOfferTypes([])
      setFunnel([])
      setRoi([])
    } finally {
      setLoading(false)
    }
  }, [tenantId])

  const [editingJourney, setEditingJourney] = useState<Partial<Journey> | null>(null)
  const [editingOffer, setEditingOffer] = useState<Partial<Offer> | null>(null)

  useEffect(() => { loadData() }, [loadData])

  const handleSaveJourney = async (form: Partial<Journey>, rules: Partial<JourneyRule>[]) => {
    try {
      if (form.id) {
        await journeyApi.updateJourney(form.id, form)
      } else {
        const created = await journeyApi.createJourney({ ...form, tenant_id: tenantId })
        if (rules.length > 0) {
          await journeyApi.addRules(
            created.journey.id,
            rules.map((r) => ({ ...r, journey_id: created.journey.id, tenant_id: tenantId }))
          )
        }
      }
      setEditingJourney(null)
      loadData()
    } catch (err) {
      console.error("Failed to save journey:", err)
    }
  }

  const handleSaveOffer = async (offer: Partial<Offer>) => {
    try {
      if ((offer as any).id) {
        await journeyApi.updateOffer((offer as any).id, offer)
      } else {
        await journeyApi.createOffer({ ...offer, tenant_id: tenantId })
      }
      setEditingOffer(null)
      loadData()
    } catch (err) {
      console.error("Failed to save offer:", err)
    }
  }

  const toggleJourneyStatus = async (journey: Journey) => {
    const newStatus = journey.status === "active" ? "paused" : "active"
    await journeyApi.updateJourney(journey.id, { status: newStatus })
    loadData()
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Zap className="h-5 w-5 animate-spin" />
          <span>Loading journey engine...</span>
        </div>
      </div>
    )
  }

  // Edit mode
  if (editingJourney) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditingJourney(null)}>
            <ArrowRight className="h-4 w-4 rotate-180" />
          </Button>
          <h3 className="text-lg font-semibold">
            {editingJourney.id ? "Edit Journey" : "Create Journey"}
          </h3>
        </div>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <JourneyBuilder
              journey={editingJourney}
              offers={offers}
              attributes={attributes}
              operators={operators}
              offerTypes={offerTypes}
              onSave={handleSaveJourney}
              onCancel={() => setEditingJourney(null)}
            />
          </CardContent>
        </Card>
      </div>
    )
  }

  // Offer edit mode
  if (editingOffer) {
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setEditingOffer(null)}>
            <ArrowRight className="h-4 w-4 rotate-180" />
          </Button>
          <h3 className="text-lg font-semibold">
            {(editingOffer as any).id ? "Edit Offer" : "Create Offer"}
          </h3>
        </div>
        <Card className="border-border bg-card">
          <CardContent className="p-4">
            <OfferConfig
              offer={editingOffer}
              onChange={setEditingOffer}
              offerTypes={offerTypes}
            />
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border mt-4">
              <Button variant="outline" size="sm" onClick={() => setEditingOffer(null)}>
                Cancel
              </Button>
              <Button size="sm" className="bg-primary gap-1" onClick={() => handleSaveOffer(editingOffer)}>
                <Save className="h-3 w-3" /> Save Offer
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Target className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-semibold">Retention Journey Engine</h2>
        </div>
        {isOffline && (
          <Badge variant="outline" className="bg-amber-500/10 text-amber-500 border-amber-500/20 text-xs">
            Offline Mode
          </Badge>
        )}
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-500">
          <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold">Service Connection Warning</p>
            <p className="text-xs text-amber-500/80">{error}</p>
          </div>
        </div>
      )}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-secondary">
          <TabsTrigger value="journeys">Journeys</TabsTrigger>
          <TabsTrigger value="offers">Offers</TabsTrigger>
          <TabsTrigger value="funnel">Funnel & Analytics</TabsTrigger>
          <TabsTrigger value="roi">ROI Report</TabsTrigger>
        </TabsList>

        {/* --- JOURNEYS TAB --- */}
        <TabsContent value="journeys" className="space-y-4 mt-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Configure rule-based retention journeys that trigger when customers cancel.
            </p>
            <Button size="sm" className="bg-primary gap-1" onClick={() => setEditingJourney(emptyJourney(tenantId))}>
              <Plus className="h-3 w-3" /> Create Journey
            </Button>
          </div>

          <div className="space-y-3">
            {journeys.map((j) => (
              <Card key={j.id} className="border-border bg-card">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold text-foreground">{j.name}</h4>
                        <Badge
                          className={
                            j.status === "active"
                              ? "bg-emerald-500/20 text-emerald-400"
                              : j.status === "paused"
                                ? "bg-amber-500/20 text-amber-400"
                                : "bg-slate-500/20 text-slate-400"
                          }
                        >
                          {j.status}
                        </Badge>
                        <Badge variant="outline" className="text-xs">
                          Priority {j.priority}
                        </Badge>
                      </div>
                      {j.description && (
                        <p className="text-sm text-muted-foreground mb-2">{j.description}</p>
                      )}
                      {j.rules && j.rules.length > 0 && (
                        <div className="flex flex-wrap gap-1 mb-2">
                          {j.rules.slice(0, 4).map((r, i) => (
                            <Badge key={i} variant="secondary" className="text-xs">
                              {r.attribute} {r.operator} {JSON.stringify(r.value)}
                            </Badge>
                          ))}
                          {j.rules.length > 4 && (
                            <Badge variant="secondary" className="text-xs">
                              +{j.rules.length - 4} more
                            </Badge>
                          )}
                        </div>
                      )}
                      <div className="flex gap-4 text-xs text-muted-foreground">
                        <span>Triggered: {j.times_triggered}</span>
                        <span>Shown: {j.times_shown}</span>
                        <span>Accepted: {j.times_accepted}</span>
                        <span>Revenue saved: R{j.revenue_preserved.toLocaleString()}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => toggleJourneyStatus(j)}>
                        {j.status === "active" ? (
                          <Pause className="h-3 w-3 text-amber-400" />
                        ) : (
                          <Play className="h-3 w-3 text-emerald-400" />
                        )}
                      </Button>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setEditingJourney(j)}>
                        <Edit3 className="h-3 w-3" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
            {journeys.length === 0 && (
              <Card className="border-border bg-card">
                <CardContent className="py-8 text-center">
                  <Target className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-muted-foreground">No journeys configured yet</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Create journeys to automatically present retention offers when customers cancel.
                  </p>
                  <Button size="sm" className="bg-primary gap-1 mt-3" onClick={() => setEditingJourney(emptyJourney(tenantId))}>
                    <Plus className="h-3 w-3" /> Create First Journey
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* --- OFFERS TAB --- */}
        <TabsContent value="offers" className="space-y-4 mt-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Manage discount offers, upgrades, pauses, and rewards.
            </p>
            <Button size="sm" className="bg-primary gap-1" onClick={() => setEditingOffer(emptyOffer())}>
              <Plus className="h-3 w-3" /> Create Offer
            </Button>
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {offers.map((o) => (
              <Card key={o.id} className="border-border bg-card">
                <CardContent className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h4 className="font-semibold text-foreground text-sm">{o.name}</h4>
                      <Badge variant="outline" className="text-xs mt-1">{o.offer_type}</Badge>
                    </div>
                    <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => setEditingOffer(o as any)}>
                      <Edit3 className="h-3 w-3" />
                    </Button>
                  </div>
                  {o.description && (
                    <p className="text-xs text-muted-foreground mb-2">{o.description}</p>
                  )}
                  <div className="space-y-1 text-xs">
                    {Object.entries(o.parameters).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-muted-foreground">{k.replace(/_/g, " ")}</span>
                        <span className="text-foreground font-medium">
                          {typeof v === "number" && k.includes("zar") ? `R${v}` : String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center gap-2 mt-3 text-xs text-muted-foreground">
                    <span>Used: {o.total_redemptions}</span>
                    {o.max_total_redemptions && <span>/ {o.max_total_redemptions}</span>}
                  </div>
                </CardContent>
              </Card>
            ))}
            {offers.length === 0 && (
              <Card className="border-border bg-card md:col-span-2 lg:col-span-3">
                <CardContent className="py-8 text-center">
                  <DollarSign className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
                  <p className="text-muted-foreground">No offers created yet</p>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        {/* --- FUNNEL TAB --- */}
        <TabsContent value="funnel" className="space-y-4 mt-4">
          {/* Summary cards */}
          <div className="grid gap-4 sm:grid-cols-4">
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Total Triggered</p>
                <p className="text-2xl font-bold text-foreground">
                  {funnel.reduce((s, f) => s + f.triggered, 0)}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Offers Shown</p>
                <p className="text-2xl font-bold text-foreground">
                  {funnel.reduce((s, f) => s + f.shown, 0)}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Accepted</p>
                <p className="text-2xl font-bold text-emerald-400">
                  {funnel.reduce((s, f) => s + f.accepted, 0)}
                </p>
              </CardContent>
            </Card>
            <Card className="border-border bg-card">
              <CardContent className="p-4">
                <p className="text-sm text-muted-foreground">Revenue Preserved</p>
                <p className="text-2xl font-bold text-blue-400">
                  R{funnel.reduce((s, f) => s + f.revenue_preserved, 0).toLocaleString()}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Funnel per journey */}
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Journey Funnel</CardTitle>
            </CardHeader>
            <CardContent>
              {funnel.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No funnel data yet</p>
              ) : (
                <div className="space-y-4">
                  {funnel.map((f) => {
                    const data = [
                      { name: "Triggered", value: f.triggered, fill: "#60a5fa" },
                      { name: "Shown", value: f.shown, fill: "#a855f7" },
                      { name: "Accepted", value: f.accepted, fill: "#4ade80" },
                      { name: "Rejected", value: f.rejected, fill: "#ef4444" },
                    ]
                    return (
                      <div key={f.journey_id || f.journey_name} className="rounded-lg border border-border p-3">
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium text-foreground text-sm">{f.journey_name}</span>
                          <Badge className="bg-emerald-500/20 text-emerald-400">
                            {f.acceptance_rate}% acceptance
                          </Badge>
                        </div>
                        <ResponsiveContainer width="100%" height={150}>
                          <BarChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                            <XAxis dataKey="name" stroke="#888" fontSize={10} />
                            <YAxis stroke="#888" fontSize={10} />
                            <Tooltip contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }} />
                            <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                              {data.map((entry, i) => (
                                <Cell key={i} fill={entry.fill} />
                              ))}
                            </Bar>
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* --- ROI TAB --- */}
        <TabsContent value="roi" className="space-y-4 mt-4">
          <Card className="border-border bg-card">
            <CardHeader>
              <CardTitle className="text-base">Return on Investment by Journey</CardTitle>
            </CardHeader>
            <CardContent>
              {roi.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-8">No ROI data yet</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-3 text-xs font-medium text-muted-foreground">Journey</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Events</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Accepted</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Rate</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Discount Cost</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">Revenue at Risk</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-muted-foreground">ROI</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roi.map((r, i) => (
                        <tr key={i} className="border-b border-border/50 hover:bg-secondary/20">
                          <td className="py-2 px-3 text-foreground">{r.journey_name}</td>
                          <td className="py-2 px-3 text-right text-muted-foreground">{r.total_events}</td>
                          <td className="py-2 px-3 text-right text-emerald-400">{r.accepted}</td>
                          <td className="py-2 px-3 text-right text-muted-foreground">{r.acceptance_rate}%</td>
                          <td className="py-2 px-3 text-right text-red-400">R{r.total_discount_cost.toLocaleString()}</td>
                          <td className="py-2 px-3 text-right text-blue-400">R{r.revenue_at_risk.toLocaleString()}</td>
                          <td className="py-2 px-3 text-right">
                            <Badge className={r.roi_percent > 100 ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}>
                              {r.roi_percent}%
                            </Badge>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
