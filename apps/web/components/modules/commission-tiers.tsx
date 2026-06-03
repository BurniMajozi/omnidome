"use client"

import { useState, useEffect, useCallback } from "react"
import { Plus, Pencil, Trash2, Percent, Layers, AlertTriangle } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { adminApi } from "@/lib/admin-api"
import type { CommissionTier } from "@/lib/admin-api"

function TierForm({ tier, onSave, onCancel }: {
  tier?: CommissionTier
  onSave: (data: { tier_name: string; min_deals: number; max_deals: number | null; rate_percent: string }) => void
  onCancel: () => void
}) {
  const [name, setName] = useState(tier?.tier_name ?? "")
  const [minDeals, setMinDeals] = useState(String(tier?.min_deals ?? 0))
  const [maxDeals, setMaxDeals] = useState(tier?.max_deals != null ? String(tier.max_deals) : "")
  const [rate, setRate] = useState(tier?.rate_percent ?? "5.00")

  return (
    <div className="space-y-4 pt-2">
      <div>
        <Label className="text-xs text-muted-foreground">Tier Name</Label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Bronze, Silver, Gold" className="mt-1" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label className="text-xs text-muted-foreground">Min Deals</Label>
          <Input type="number" min={0} value={minDeals} onChange={(e) => setMinDeals(e.target.value)} className="mt-1" />
        </div>
        <div>
          <Label className="text-xs text-muted-foreground">Max Deals (empty = no limit)</Label>
          <Input type="number" min={0} value={maxDeals} onChange={(e) => setMaxDeals(e.target.value)} placeholder="∞" className="mt-1" />
        </div>
      </div>
      <div>
        <Label className="text-xs text-muted-foreground">Commission Rate (%)</Label>
        <Input type="number" min={0} max={100} step={0.5} value={rate} onChange={(e) => setRate(e.target.value)} className="mt-1" />
      </div>
      <div className="flex gap-2 justify-end">
        <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button size="sm" onClick={() => onSave({
          tier_name: name,
          min_deals: parseInt(minDeals) || 0,
          max_deals: maxDeals ? parseInt(maxDeals) : null,
          rate_percent: rate,
        })} disabled={!name || !rate}>
          {tier ? "Update" : "Create"} Tier
        </Button>
      </div>
    </div>
  )
}

export function CommissionTiers() {
  const [tiers, setTiers] = useState<CommissionTier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editTier, setEditTier] = useState<CommissionTier | null>(null)
  const [showCreate, setShowCreate] = useState(false)

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const data = await adminApi.listCommissionTiers()
      setTiers(data)
      setError(null)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load tiers")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleCreate = async (data: { tier_name: string; min_deals: number; max_deals: number | null; rate_percent: string }) => {
    await adminApi.createCommissionTier(data)
    setShowCreate(false)
    load()
  }

  const handleUpdate = async (data: { tier_name: string; min_deals: number; max_deals: number | null; rate_percent: string }) => {
    if (!editTier) return
    await adminApi.updateCommissionTier(editTier.id, data)
    setEditTier(null)
    load()
  }

  const handleDelete = async (tierId: string) => {
    if (!confirm("Delete this commission tier?")) return
    await adminApi.deleteCommissionTier(tierId)
    load()
  }

  const handleToggleActive = async (tier: CommissionTier) => {
    await adminApi.updateCommissionTier(tier.id, { is_active: !tier.is_active })
    load()
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Percent className="h-5 w-5 text-violet-400" />
            Commission Tiers
          </h3>
          <p className="text-sm text-muted-foreground">Configure commission rates based on monthly deal count</p>
        </div>
        <Dialog open={showCreate} onOpenChange={setShowCreate}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="mr-2 h-4 w-4" /> Add Tier</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Create Commission Tier</DialogTitle></DialogHeader>
            <TierForm onSave={handleCreate} onCancel={() => setShowCreate(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {error && (
        <Card className="border-amber-500/30 bg-amber-500/10">
          <CardContent className="p-3 flex items-center gap-2 text-amber-400 text-sm">
            <AlertTriangle className="h-4 w-4" /> {error}
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="text-sm text-muted-foreground py-8 text-center">Loading tiers…</div>
      ) : tiers.length === 0 ? (
        <Card className="border-border bg-card">
          <CardContent className="py-12 text-center">
            <Layers className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
            <p className="text-muted-foreground">No commission tiers configured</p>
            <p className="text-xs text-muted-foreground mt-1">Add a tier to get started, or the system will use default rates</p>
            <div className="mt-4 text-xs text-muted-foreground bg-secondary/30 rounded-lg p-3 max-w-md mx-auto">
              <p className="font-medium mb-1">Default fallback tiers:</p>
              <p>0–9 deals: 5% • 10–19 deals: 7% • 20+ deals: 10%</p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tier</TableHead>
                <TableHead>Deal Range</TableHead>
                <TableHead>Rate</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tiers.map((tier) => (
                <Dialog key={tier.id}>
                  <TableRow className={tier.is_active ? "" : "opacity-50"}>
                    <TableCell className="font-medium">{tier.tier_name}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {tier.min_deals}–{tier.max_deals ?? "∞"} deals
                    </TableCell>
                    <TableCell className="font-mono text-sm">{tier.rate_percent}%</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch checked={tier.is_active} onCheckedChange={() => handleToggleActive(tier)} />
                        <Badge className={tier.is_active ? "bg-emerald-500/20 text-emerald-400" : "bg-secondary text-muted-foreground"}>
                          {tier.is_active ? "Active" : "Inactive"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <DialogTrigger asChild>
                          <Button variant="ghost" size="icon" onClick={() => setEditTier(tier)}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        </DialogTrigger>
                        <Button variant="ghost" size="icon" onClick={() => handleDelete(tier.id)}>
                          <Trash2 className="h-3.5 w-3.5 text-red-400" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                  <DialogContent>
                    <DialogHeader><DialogTitle>Edit Commission Tier</DialogTitle></DialogHeader>
                    <TierForm tier={editTier ?? undefined} onSave={handleUpdate} onCancel={() => setEditTier(null)} />
                  </DialogContent>
                </Dialog>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      <Card className="border-border bg-card">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs text-muted-foreground">How Commission Tiers Work</CardTitle>
        </CardHeader>
        <CardContent className="text-xs text-muted-foreground space-y-1.5">
          <p>• Tiers are matched by monthly won deal count (calendar month)</p>
          <p>• The highest matching rate is applied when a deal is closed won</p>
          <p>• If no tiers are configured, default rates apply: 5% / 7% / 10%</p>
          <p>• Set max deals to empty for an open-ended top tier</p>
          <p>• Inactive tiers are ignored but preserved for history</p>
        </CardContent>
      </Card>
    </div>
  )
}
