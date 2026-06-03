"use client"

import { useState, useEffect, useCallback } from "react"
import {
  Search, Plus, Phone, Mail, MapPin, ChevronRight, DollarSign,
  FileText, Users, TrendingUp, Clock, CheckCircle, AlertCircle,
  ArrowLeft, Send, Package, Star, BarChart3, Target,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { fieldSalesApi } from "@/lib/mobile-field-sales-api"
import type { MobileLead, MobileContact, MobileDeal, MobileQuote, Customer360, MobileCommission } from "@/lib/mobile-field-sales-api"

// ── Lead Card ─────────────────────────────────────────────────────────

function LeadCard({ lead, onConvert, onView }: { lead: MobileLead; onConvert: (l: MobileLead) => void; onView: (l: MobileLead) => void }) {
  const interestColors = ["", "bg-red-500/20 text-red-400", "bg-orange-500/20 text-orange-400", "bg-yellow-500/20 text-yellow-400", "bg-lime-500/20 text-lime-400", "bg-emerald-500/20 text-emerald-400"]
  return (
    <Card className="border-border bg-card">
      <CardContent className="p-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm text-foreground truncate">{lead.first_name} {lead.last_name}</p>
              <Badge className={`text-[10px] px-1.5 py-0 ${interestColors[lead.interest_level] || "bg-secondary"}`}>
                {"★".repeat(lead.interest_level)}
              </Badge>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
              {lead.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{lead.phone}</span>}
              {lead.source && <span className="flex items-center gap-1"><Target className="h-3 w-3" />{lead.source}</span>}
            </div>
            {lead.address && <p className="text-xs text-muted-foreground mt-1 truncate flex items-center gap-1"><MapPin className="h-3 w-3 shrink-0" />{lead.address}</p>}
          </div>
          <div className="flex gap-1 ml-2">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onView(lead)}><ChevronRight className="h-3.5 w-3.5" /></Button>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => onConvert(lead)}><DollarSign className="h-3.5 w-3.5 text-emerald-400" /></Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

// ── Customer 360 Panel ────────────────────────────────────────────────

function Customer360Panel({ contact, onClose }: { contact: Customer360; onClose: () => void }) {
  const outstandingBilling = contact.billing?.filter(b => b.status !== "PAID") || []
  const openSupport = contact.support?.filter(s => s.status !== "CLOSED") || []
  const lifecycle = contact.lifecycle_data

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={onClose}><ArrowLeft className="h-4 w-4" /></Button>
        <div>
          <h3 className="font-semibold text-foreground">{contact.first_name} {contact.last_name}</h3>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            {contact.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{contact.phone}</span>}
            {contact.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{contact.email}</span>}
          </div>
        </div>
      </div>

      {/* Tags */}
      {contact.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {contact.tags.map(tag => (
            <Badge key={tag} variant="secondary" className="text-[10px]">{tag}</Badge>
          ))}
        </div>
      )}

      {/* Lifecycle + Health */}
      <div className="grid grid-cols-2 gap-2">
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <p className="text-lg font-bold text-emerald-400">{lifecycle?.current_stage || "N/A"}</p>
          <p className="text-xs text-muted-foreground">Lifecycle Stage</p>
        </CardContent></Card>
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <p className="text-lg font-bold text-violet-400">{lifecycle?.health_score ?? "N/A"}</p>
          <p className="text-xs text-muted-foreground">Health Score</p>
        </CardContent></Card>
      </div>

      {lifecycle?.churn_probability != null && lifecycle.churn_probability > 0.5 && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-2 text-xs text-red-400">
          ⚠️ High churn risk ({(lifecycle.churn_probability * 100).toFixed(0)}%)
        </div>
      )}

      {/* Network Services */}
      {contact.network.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">SERVICES ({contact.network.length})</h4>
          <div className="space-y-2">
            {contact.network.map(s => (
              <div key={s.id} className="flex items-center justify-between bg-secondary/30 rounded-lg p-2">
                <div><p className="text-sm font-medium">{s.fno_reference || s.id}</p></div>
                <Badge className={`text-[10px] ${s.status === "ACTIVE" ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>{s.status}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Outstanding Billing */}
      {outstandingBilling.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">OUTSTANDING INVOICES ({outstandingBilling.length})</h4>
          <div className="space-y-2">
            {outstandingBilling.map(inv => (
              <div key={inv.id} className="flex items-center justify-between bg-amber-500/10 border border-amber-500/20 rounded-lg p-2">
                <div><p className="text-sm font-medium">{inv.invoice_number}</p><p className="text-xs text-muted-foreground">Due: {inv.due_date}</p></div>
                <p className="text-sm font-bold text-amber-400">R{inv.total_amount.toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open Support Tickets */}
      {openSupport.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">OPEN TICKETS ({openSupport.length})</h4>
          <div className="space-y-2">
            {openSupport.map(t => (
              <div key={t.id} className="flex items-center justify-between bg-secondary/30 rounded-lg p-2">
                <div><p className="text-sm font-medium">{t.subject}</p></div>
                <Badge className={`text-[10px] ${t.priority === "HIGH" || t.priority === "URGENT" ? "bg-red-500/20 text-red-400" : "bg-blue-500/20 text-blue-400"}`}>{t.priority}</Badge>
              </div>
            ))}
          </div>
        </div>
      )}

      {contact.notes_count > 0 && (
        <p className="text-xs text-muted-foreground">{contact.notes_count} notes</p>
      )}
    </div>
  )
}

// ── Quote Builder ─────────────────────────────────────────────────────

function QuoteBuilder({ customerId, onDone }: { customerId: string; onDone: () => void }) {
  const [products, setProducts] = useState<Array<{ id: string; name: string; monthly_price: number; setup_fee: number }>>([])
  const [selected, setSelected] = useState<Array<{ product_id: string; name: string; monthly_price: number; qty: number }>>([])
  const [term, setTerm] = useState("12")

  useEffect(() => {
    fieldSalesApi.listProducts().then(setProducts).catch(() => {})
  }, [])

  const addProduct = (p: { id: string; name: string; monthly_price: number }) => {
    if (selected.find(s => s.product_id === p.id)) return
    setSelected([...selected, { product_id: p.id, name: p.name, monthly_price: p.monthly_price, qty: 1 }])
  }

  const removeProduct = (id: string) => setSelected(selected.filter(s => s.product_id !== id))
  const updateQty = (id: string, qty: number) => setSelected(selected.map(s => s.product_id === id ? { ...s, qty: Math.max(1, qty) } : s))

  const totalMonthly = selected.reduce((s, i) => s + i.monthly_price * i.qty, 0)
  const totalOnceOff = selected.reduce((s, i) => s + i.setup_fee * i.qty, 0)

  const handleSend = async () => {
    await fieldSalesApi.createQuote({ customer_id: customerId, items: selected, term_months: parseInt(term) })
    onDone()
  }

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-medium text-muted-foreground mb-2">SELECT PRODUCTS</h4>
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {products.map(p => (
            <button key={p.id} onClick={() => addProduct(p)} className="w-full flex items-center justify-between bg-secondary/30 hover:bg-secondary/50 rounded-lg p-2 text-left">
              <div><p className="text-sm">{p.name}</p></div>
              <p className="text-sm font-medium text-emerald-400">R{p.monthly_price}/mo</p>
            </button>
          ))}
          {products.length === 0 && <p className="text-xs text-muted-foreground text-center py-4">No products loaded</p>}
        </div>
      </div>

      {selected.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground mb-2">QUOTE ITEMS</h4>
          <div className="space-y-2">
            {selected.map(item => (
              <div key={item.product_id} className="flex items-center justify-between bg-card border border-border rounded-lg p-2">
                <div className="flex-1"><p className="text-sm">{item.name}</p><p className="text-xs text-muted-foreground">R{item.monthly_price}/mo</p></div>
                <div className="flex items-center gap-2">
                  <Input type="number" min={1} value={item.qty} onChange={e => updateQty(item.product_id, parseInt(e.target.value) || 1)} className="w-14 h-7 text-xs text-center" />
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeProduct(item.product_id)}>×</Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Label className="text-xs text-muted-foreground">Term</Label>
        <Select value={term} onValueChange={setTerm}>
          <SelectTrigger className="w-24 h-8"><SelectValue /></SelectTrigger>
          <SelectContent><SelectItem value="12">12 mo</SelectItem><SelectItem value="24">24 mo</SelectItem></SelectContent>
        </Select>
      </div>

      <Card className="border-border bg-card"><CardContent className="p-3 space-y-1">
        <div className="flex justify-between text-sm"><span className="text-muted-foreground">Monthly</span><span className="font-bold">R{totalMonthly.toLocaleString()}</span></div>
        <div className="flex justify-between text-sm"><span className="text-muted-foreground">Once-off</span><span className="font-bold">R{totalOnceOff.toLocaleString()}</span></div>
      </CardContent></Card>

      <Button className="w-full" disabled={selected.length === 0} onClick={handleSend}><Send className="mr-2 h-4 w-4" /> Send Quote</Button>
    </div>
  )
}

// ── Main Field Sales App ──────────────────────────────────────────────

export function FieldSalesApp() {
  const [tab, setTab] = useState("leads")
  const [leads, setLeads] = useState<MobileLead[]>([])
  const [contacts, setContacts] = useState<MobileContact[]>([])
  const [deals, setDeals] = useState<MobileDeal[]>([])
  const [commissions, setCommissions] = useState<MobileCommission[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState("")
  const [selectedContact, setSelectedContact] = useState<Customer360 | null>(null)
  const [convertLead, setConvertLead] = useState<MobileLead | null>(null)
  const [quoteContactId, setQuoteContactId] = useState<string | null>(null)
  const [showNewLead, setShowNewLead] = useState(false)
  const [newLead, setNewLead] = useState({ first_name: "", last_name: "", email: "", phone: "", source: "Field Visit", address: "" })

  const load = useCallback(async () => {
    try {
      setLoading(true)
      const [l, c, d, co] = await Promise.all([
        fieldSalesApi.listLeads({ status: "NEW" }),
        fieldSalesApi.listContacts({ limit: 50 }),
        fieldSalesApi.listDeals({ status: "OPEN" }),
        fieldSalesApi.getMyCommissions(),
      ])
      setLeads(l); setContacts(c); setDeals(d); setCommissions(co)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleConvert = async (lead: MobileLead) => {
    try {
      await fieldSalesApi.convertLead(lead.id, { name: `${lead.first_name} ${lead.last_name} - New Deal`, value_zar: 0 })
      setConvertLead(null); load()
    } catch (e) { alert("Convert failed: " + (e as Error).message) }
  }

  const handleViewContact = async (contactId: string) => {
    try {
      const data = await fieldSalesApi.getCustomer360(contactId)
      setSelectedContact(data)
    } catch { /* fallback: build minimal 360 from list data */ }
  }

  const handleCreateLead = async () => {
    if (!newLead.first_name) return
    try {
      await fieldSalesApi.createLead(newLead)
      setShowNewLead(false); setNewLead({ first_name: "", last_name: "", email: "", phone: "", source: "Field Visit", address: "" }); load()
    } catch (e) { alert("Create failed: " + (e as Error).message) }
  }

  const filteredLeads = leads.filter(l => `${l.first_name} ${l.last_name} ${l.phone} ${l.address}`.toLowerCase().includes(search.toLowerCase()))
  const filteredContacts = contacts.filter(c => `${c.first_name} ${c.last_name} ${c.phone}`.toLowerCase().includes(search.toLowerCase()))

  if (selectedContact) {
    return <Customer360Panel contact={selectedContact} onClose={() => setSelectedContact(null)} />
  }

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="grid grid-cols-3 gap-2">
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <Users className="h-4 w-4 text-violet-400 mx-auto mb-1" />
          <p className="text-lg font-bold">{leads.length}</p><p className="text-[10px] text-muted-foreground">New Leads</p>
        </CardContent></Card>
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <TrendingUp className="h-4 w-4 text-emerald-400 mx-auto mb-1" />
          <p className="text-lg font-bold">{deals.length}</p><p className="text-[10px] text-muted-foreground">Open Deals</p>
        </CardContent></Card>
        <Card className="border-border bg-card"><CardContent className="p-3 text-center">
          <DollarSign className="h-4 w-4 text-amber-400 mx-auto mb-1" />
          <p className="text-lg font-bold">R{commissions.filter(c => c.status === "PENDING").reduce((s, c) => s + c.amount_zar, 0).toLocaleString()}</p>
          <p className="text-[10px] text-muted-foreground">Pending Comm</p>
        </CardContent></Card>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input placeholder="Search leads, contacts..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-secondary w-full">
          <TabsTrigger value="leads" className="flex-1">Leads</TabsTrigger>
          <TabsTrigger value="contacts" className="flex-1">Customers</TabsTrigger>
          <TabsTrigger value="deals" className="flex-1">Deals</TabsTrigger>
          <TabsTrigger value="commissions" className="flex-1">Commissions</TabsTrigger>
        </TabsList>

        <TabsContent value="leads" className="mt-3 space-y-2">
          <div className="flex justify-between items-center">
            <p className="text-xs text-muted-foreground">{filteredLeads.length} new leads</p>
            <Dialog open={showNewLead} onOpenChange={setShowNewLead}>
              <DialogTrigger asChild><Button size="sm"><Plus className="mr-1 h-3 w-3" /> New Lead</Button></DialogTrigger>
              <DialogContent>
                <DialogHeader><DialogTitle>New Lead</DialogTitle></DialogHeader>
                <div className="space-y-3 pt-2">
                  <div className="grid grid-cols-2 gap-2">
                    <div><Label className="text-xs">First Name *</Label><Input value={newLead.first_name} onChange={e => setNewLead({ ...newLead, first_name: e.target.value })} className="mt-1" /></div>
                    <div><Label className="text-xs">Last Name</Label><Input value={newLead.last_name} onChange={e => setNewLead({ ...newLead, last_name: e.target.value })} className="mt-1" /></div>
                  </div>
                  <div><Label className="text-xs">Phone</Label><Input value={newLead.phone} onChange={e => setNewLead({ ...newLead, phone: e.target.value })} className="mt-1" /></div>
                  <div><Label className="text-xs">Email</Label><Input value={newLead.email} onChange={e => setNewLead({ ...newLead, email: e.target.value })} className="mt-1" /></div>
                  <div><Label className="text-xs">Address</Label><Input value={newLead.address} onChange={e => setNewLead({ ...newLead, address: e.target.value })} className="mt-1" /></div>
                  <Button className="w-full" onClick={handleCreateLead} disabled={!newLead.first_name}>Create Lead</Button>
                </div>
              </DialogContent>
            </Dialog>
          </div>
          {loading ? <p className="text-xs text-muted-foreground text-center py-8">Loading...</p> : filteredLeads.map(l => (
            <LeadCard key={l.id} lead={l} onConvert={setConvertLead} onView={lead => handleViewContact(lead.id)} />
          ))}
          {!loading && filteredLeads.length === 0 && <p className="text-xs text-muted-foreground text-center py-8">No new leads</p>}
        </TabsContent>

        <TabsContent value="contacts" className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">{filteredContacts.length} contacts</p>
          {filteredContacts.map(c => (
            <Card key={c.id} className="border-border bg-card cursor-pointer hover:border-primary/50" onClick={() => handleViewContact(c.id)}>
              <CardContent className="p-3 flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm">{c.first_name} {c.last_name}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {c.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{c.phone}</span>}
                    {c.rica_verified && <Badge className="text-[10px] bg-emerald-500/20 text-emerald-400">RICA ✓</Badge>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={e => { e.stopPropagation(); setQuoteContactId(c.id) }}><FileText className="h-3.5 w-3.5 text-violet-400" /></Button>
                  <ChevronRight className="h-4 w-4 text-muted-foreground self-center" />
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="deals" className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">{deals.length} open deals</p>
          {deals.map(d => (
            <Card key={d.id} className="border-border bg-card">
              <CardContent className="p-3">
                <div className="flex items-center justify-between">
                  <div><p className="font-medium text-sm">{d.name}</p><p className="text-xs text-muted-foreground">{d.stage_name}</p></div>
                  <div className="text-right"><p className="text-sm font-bold text-emerald-400">R{d.value_zar.toLocaleString()}</p><Badge className="text-[10px] bg-blue-500/20 text-blue-400">{d.status}</Badge></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </TabsContent>

        <TabsContent value="commissions" className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">Your commissions</p>
          {commissions.map(c => (
            <Card key={c.id} className="border-border bg-card">
              <CardContent className="p-3 flex items-center justify-between">
                <div><p className="text-sm font-medium">R{c.amount_zar.toLocaleString()}</p><p className="text-xs text-muted-foreground">{c.rate_percent}% rate</p></div>
                <Badge className={`text-[10px] ${c.status === "PAID" ? "bg-emerald-500/20 text-emerald-400" : c.status === "PENDING" ? "bg-amber-500/20 text-amber-400" : "bg-secondary"}`}>{c.status}</Badge>
              </CardContent>
            </Card>
          ))}
          {commissions.length === 0 && <p className="text-xs text-muted-foreground text-center py-8">No commissions yet</p>}
        </TabsContent>
      </Tabs>

      {/* Convert Lead Dialog */}
      <Dialog open={!!convertLead} onOpenChange={() => setConvertLead(null)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Convert Lead to Deal</DialogTitle></DialogHeader>
          {convertLead && (
            <div className="space-y-3 pt-2">
              <p className="text-sm text-muted-foreground">Convert <strong>{convertLead.first_name} {convertLead.last_name}</strong> into a deal?</p>
              <Button className="w-full" onClick={() => handleConvert(convertLead)}>Create Deal</Button>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Quote Builder Dialog */}
      <Dialog open={!!quoteContactId} onOpenChange={() => setQuoteContactId(null)}>
        <DialogContent className="max-h-[80vh] overflow-y-auto">
          <DialogHeader><DialogTitle>Build Quote</DialogTitle></DialogHeader>
          {quoteContactId && <QuoteBuilder customerId={quoteContactId} onDone={() => { setQuoteContactId(null); load() }} />}
        </DialogContent>
      </Dialog>
    </div>
  )
}
