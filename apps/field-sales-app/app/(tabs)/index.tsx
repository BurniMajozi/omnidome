"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Search, Plus, Phone, Mail, MapPin, ChevronRight, DollarSign,
  FileText, Users, TrendingUp, ArrowLeft, Send, Star, Target, X,
} from "lucide-react";
import { fieldSalesApi } from "@/lib/api/client";
import type {
  MobileLead, MobileContact, MobileDeal, Customer360, MobileCommission,
} from "@/lib/api/types";

/* ─── Inline UI primitives (no shadcn) ─────────────────────────────── */

function UICard({ children, className = "", onClick }: { children: React.ReactNode; className?: string; onClick?: () => void }) {
  return (
    <div
      className={`border border-[#334155] bg-[#1e293b] rounded-xl ${onClick ? "cursor-pointer hover:border-emerald-500/50" : ""} ${className}`}
      onClick={onClick}
    >
      {children}
    </div>
  );
}

function UIBadge({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium ${className}`}>
      {children}
    </span>
  );
}

function UIButton({ children, onClick, disabled = false, className = "", variant = "primary", size = "md" }: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean; className?: string;
  variant?: "primary" | "ghost" | "secondary"; size?: "sm" | "md" | "icon";
}) {
  const base = "inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-emerald-600 hover:bg-emerald-700 text-white",
    ghost: "bg-transparent hover:bg-white/10 text-slate-300",
    secondary: "bg-slate-700 hover:bg-slate-600 text-slate-200",
  };
  const sizes = {
    sm: "h-8 px-3 text-xs",
    md: "h-10 px-4 text-sm",
    icon: "h-8 w-8 p-0",
  };
  return (
    <button onClick={onClick} disabled={disabled} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}>
      {children}
    </button>
  );
}

function UIInput({ value, onChange, placeholder, type = "text", className = "", min }: {
  value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; placeholder?: string;
  type?: string; className?: string; min?: number;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      min={min}
      className={`w-full h-10 rounded-lg border border-[#334155] bg-[#0f172a] px-3 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-emerald-500 ${className}`}
    />
  );
}

function UISelect({ value, onChange, children }: { value: string; onChange: (v: string) => void; children: React.ReactNode }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-lg border border-[#334155] bg-[#0f172a] px-2 text-xs text-slate-100 focus:outline-none focus:border-emerald-500"
    >
      {children}
    </select>
  );
}

function UIDialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="w-full max-w-md bg-[#1e293b] border border-[#334155] rounded-2xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-4 border-b border-[#334155]">
          <h3 className="text-base font-semibold text-slate-100">{title}</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}

function UILabel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <label className={`text-xs text-slate-400 ${className}`}>{children}</label>;
}

/* ─── Lead Card ─────────────────────────────────────────────────────── */

function LeadCard({ lead, onConvert, onView }: { lead: MobileLead; onConvert: (l: MobileLead) => void; onView: (l: MobileLead) => void }) {
  const interestColors = ["", "bg-red-500/20 text-red-400", "bg-orange-500/20 text-orange-400", "bg-yellow-500/20 text-yellow-400", "bg-lime-500/20 text-lime-400", "bg-emerald-500/20 text-emerald-400"];
  return (
    <UICard className="overflow-hidden">
      <div className="p-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <p className="font-medium text-sm text-slate-100 truncate">{lead.first_name} {lead.last_name}</p>
              <UIBadge className={`${interestColors[lead.interest_level] || "bg-slate-700 text-slate-300"}`}>
                {"★".repeat(lead.interest_level)}
              </UIBadge>
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
              {lead.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{lead.phone}</span>}
              {lead.source && <span className="flex items-center gap-1"><Target className="h-3 w-3" />{lead.source}</span>}
            </div>
            {lead.address && <p className="text-xs text-slate-400 mt-1 truncate flex items-center gap-1"><MapPin className="h-3 w-3 shrink-0" />{lead.address}</p>}
          </div>
          <div className="flex gap-1 ml-2">
            <UIButton variant="ghost" size="icon" onClick={() => onView(lead)}><ChevronRight className="h-3.5 w-3.5" /></UIButton>
            <UIButton variant="ghost" size="icon" onClick={() => onConvert(lead)}><DollarSign className="h-3.5 w-3.5 text-emerald-400" /></UIButton>
          </div>
        </div>
      </div>
    </UICard>
  );
}

/* ─── Customer 360 Panel ────────────────────────────────────────────── */

function Customer360Panel({ contact, onClose }: { contact: Customer360; onClose: () => void }) {
  const outstandingBilling = contact.billing?.filter(b => b.status !== "PAID") || [];
  const openSupport = contact.support?.filter(s => s.status !== "CLOSED") || [];
  const lifecycle = contact.lifecycle_data;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <UIButton variant="ghost" size="icon" onClick={onClose}><ArrowLeft className="h-4 w-4" /></UIButton>
        <div>
          <h3 className="font-semibold text-slate-100">{contact.first_name} {contact.last_name}</h3>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            {contact.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{contact.phone}</span>}
            {contact.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{contact.email}</span>}
          </div>
        </div>
      </div>

      {contact.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {contact.tags.map(tag => (
            <UIBadge key={tag} className="bg-slate-700 text-slate-300 text-[10px]">{tag}</UIBadge>
          ))}
        </div>
      )}

      {/* Lifecycle + Health */}
      <div className="grid grid-cols-2 gap-2">
        <UICard><div className="p-3 text-center">
          <p className="text-lg font-bold text-emerald-400">{lifecycle?.current_stage || "N/A"}</p>
          <p className="text-xs text-slate-400">Lifecycle Stage</p>
        </div></UICard>
        <UICard><div className="p-3 text-center">
          <p className="text-lg font-bold text-violet-400">{lifecycle?.health_score ?? "N/A"}</p>
          <p className="text-xs text-slate-400">Health Score</p>
        </div></UICard>
      </div>

      {lifecycle?.churn_probability != null && lifecycle.churn_probability > 0.5 && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-2 text-xs text-red-400">
          ⚠️ High churn risk ({(lifecycle.churn_probability * 100).toFixed(0)}%)
        </div>
      )}

      {/* Network Services */}
      {contact.network.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-400 mb-2">SERVICES ({contact.network.length})</h4>
          <div className="space-y-2">
            {contact.network.map(s => (
              <div key={s.id} className="flex items-center justify-between bg-slate-700/30 rounded-lg p-2">
                <div><p className="text-sm font-medium text-slate-100">{s.fno_reference || s.id}</p></div>
                <UIBadge className={`text-[10px] ${s.status === "ACTIVE" ? "bg-emerald-500/20 text-emerald-400" : "bg-amber-500/20 text-amber-400"}`}>{s.status}</UIBadge>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Outstanding Billing */}
      {outstandingBilling.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-400 mb-2">OUTSTANDING INVOICES ({outstandingBilling.length})</h4>
          <div className="space-y-2">
            {outstandingBilling.map(inv => (
              <div key={inv.id} className="flex items-center justify-between bg-amber-500/10 border border-amber-500/20 rounded-lg p-2">
                <div><p className="text-sm font-medium text-slate-100">{inv.invoice_number}</p><p className="text-xs text-slate-400">Due: {inv.due_date}</p></div>
                <p className="text-sm font-bold text-amber-400">R{inv.total_amount.toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Open Support Tickets */}
      {openSupport.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-400 mb-2">OPEN TICKETS ({openSupport.length})</h4>
          <div className="space-y-2">
            {openSupport.map(t => (
              <div key={t.id} className="flex items-center justify-between bg-slate-700/30 rounded-lg p-2">
                <div><p className="text-sm font-medium text-slate-100">{t.subject}</p></div>
                <UIBadge className={`text-[10px] ${t.priority === "HIGH" || t.priority === "URGENT" ? "bg-red-500/20 text-red-400" : "bg-blue-500/20 text-blue-400"}`}>{t.priority}</UIBadge>
              </div>
            ))}
          </div>
        </div>
      )}

      {contact.notes_count > 0 && (
        <p className="text-xs text-slate-400">{contact.notes_count} notes</p>
      )}
    </div>
  );
}

/* ─── Quote Builder ─────────────────────────────────────────────────── */

function QuoteBuilder({ customerId, onDone }: { customerId: string; onDone: () => void }) {
  const [products, setProducts] = useState<Array<{ id: string; name: string; monthly_price: number; setup_fee: number }>>([]);
  const [selected, setSelected] = useState<Array<{ product_id: string; name: string; monthly_price: number; qty: number }>>([]);
  const [term, setTerm] = useState("12");

  useEffect(() => {
    fieldSalesApi.listProducts().then(setProducts).catch(() => {});
  }, []);

  const addProduct = (p: { id: string; name: string; monthly_price: number }) => {
    if (selected.find(s => s.product_id === p.id)) return;
    setSelected([...selected, { product_id: p.id, name: p.name, monthly_price: p.monthly_price, qty: 1 }]);
  };

  const removeProduct = (id: string) => setSelected(selected.filter(s => s.product_id !== id));
  const updateQty = (id: string, qty: number) => setSelected(selected.map(s => s.product_id === id ? { ...s, qty: Math.max(1, qty) } : s));

  const totalMonthly = selected.reduce((s, i) => s + i.monthly_price * i.qty, 0);
  const totalOnceOff = selected.reduce((s, i) => s + (products.find(p => p.id === i.product_id)?.setup_fee || 0) * i.qty, 0);

  const handleSend = async () => {
    await fieldSalesApi.createQuote({ customer_id: customerId, items: selected, term_months: parseInt(term) });
    onDone();
  };

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-medium text-slate-400 mb-2">SELECT PRODUCTS</h4>
        <div className="space-y-1 max-h-40 overflow-y-auto">
          {products.map(p => (
            <button key={p.id} onClick={() => addProduct(p)} className="w-full flex items-center justify-between bg-slate-700/30 hover:bg-slate-700/50 rounded-lg p-2 text-left">
              <div><p className="text-sm text-slate-100">{p.name}</p></div>
              <p className="text-sm font-medium text-emerald-400">R{p.monthly_price}/mo</p>
            </button>
          ))}
          {products.length === 0 && <p className="text-xs text-slate-400 text-center py-4">No products loaded</p>}
        </div>
      </div>

      {selected.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-400 mb-2">QUOTE ITEMS</h4>
          <div className="space-y-2">
            {selected.map(item => (
              <div key={item.product_id} className="flex items-center justify-between bg-[#1e293b] border border-[#334155] rounded-lg p-2">
                <div className="flex-1"><p className="text-sm text-slate-100">{item.name}</p><p className="text-xs text-slate-400">R{item.monthly_price}/mo</p></div>
                <div className="flex items-center gap-2">
                  <input type="number" min={1} value={item.qty} onChange={e => updateQty(item.product_id, parseInt(e.target.value) || 1)} className="w-14 h-7 text-xs text-center rounded border border-[#334155] bg-[#0f172a] text-slate-100" />
                  <UIButton variant="ghost" size="icon" onClick={() => removeProduct(item.product_id)}><X className="h-4 w-4 text-slate-400" /></UIButton>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <UILabel>Term</UILabel>
        <UISelect value={term} onChange={setTerm}>
          <option value="12">12 mo</option>
          <option value="24">24 mo</option>
        </UISelect>
      </div>

      <UICard><div className="p-3 space-y-1">
        <div className="flex justify-between text-sm"><span className="text-slate-400">Monthly</span><span className="font-bold text-slate-100">R{totalMonthly.toLocaleString()}</span></div>
        <div className="flex justify-between text-sm"><span className="text-slate-400">Once-off</span><span className="font-bold text-slate-100">R{totalOnceOff.toLocaleString()}</span></div>
      </div></UICard>

      <UIButton className="w-full" disabled={selected.length === 0} onClick={handleSend}><Send className="mr-2 h-4 w-4" /> Send Quote</UIButton>
    </div>
  );
}

/* ─── Leads Tab (main page) ─────────────────────────────────────────── */

export default function LeadsTab() {
  const [leads, setLeads] = useState<MobileLead[]>([]);
  const [contacts, setContacts] = useState<MobileContact[]>([]);
  const [deals, setDeals] = useState<MobileDeal[]>([]);
  const [commissions, setCommissions] = useState<MobileCommission[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedContact, setSelectedContact] = useState<Customer360 | null>(null);
  const [convertLead, setConvertLead] = useState<MobileLead | null>(null);
  const [quoteContactId, setQuoteContactId] = useState<string | null>(null);
  const [showNewLead, setShowNewLead] = useState(false);
  const [newLead, setNewLead] = useState({ first_name: "", last_name: "", email: "", phone: "", source: "Field Visit", address: "" });

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [l, c, d, co] = await Promise.all([
        fieldSalesApi.listLeads({ status: "NEW" }),
        fieldSalesApi.listContacts({ limit: 50 }),
        fieldSalesApi.listDeals({ status: "OPEN" }),
        fieldSalesApi.getMyCommissions(),
      ]);
      setLeads(l); setContacts(c); setDeals(d); setCommissions(co);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Polling fallback — refresh leads/deals every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      fieldSalesApi.listLeads({ status: "NEW" }).then(setLeads).catch(() => {});
      fieldSalesApi.listDeals({ status: "OPEN" }).then(setDeals).catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleConvert = async (lead: MobileLead) => {
    try {
      await fieldSalesApi.convertLead(lead.id, { name: `${lead.first_name} ${lead.last_name} - New Deal`, value_zar: 0 });
      setConvertLead(null); load();
    } catch (e) { alert("Convert failed: " + (e as Error).message); }
  };

  const handleViewContact = async (contactId: string) => {
    try {
      const data = await fieldSalesApi.getCustomer360(contactId);
      setSelectedContact(data);
    } catch { /* fallback: build minimal 360 from list data */ }
  };

  const handleCreateLead = async () => {
    if (!newLead.first_name) return;
    try {
      await fieldSalesApi.createLead(newLead);
      setShowNewLead(false); setNewLead({ first_name: "", last_name: "", email: "", phone: "", source: "Field Visit", address: "" }); load();
    } catch (e) { alert("Create failed: " + (e as Error).message); }
  };

  const filteredLeads = leads.filter(l => `${l.first_name} ${l.last_name} ${l.phone} ${l.address}`.toLowerCase().includes(search.toLowerCase()));
  const filteredContacts = contacts.filter(c => `${c.first_name} ${c.last_name} ${c.phone}`.toLowerCase().includes(search.toLowerCase()));

  if (selectedContact) {
    return <Customer360Panel contact={selectedContact} onClose={() => setSelectedContact(null)} />;
  }

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="grid grid-cols-3 gap-2">
        <UICard><div className="p-3 text-center">
          <Users className="h-4 w-4 text-violet-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-slate-100">{leads.length}</p><p className="text-[10px] text-slate-400">New Leads</p>
        </div></UICard>
        <UICard><div className="p-3 text-center">
          <TrendingUp className="h-4 w-4 text-emerald-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-slate-100">{deals.length}</p><p className="text-[10px] text-slate-400">Open Deals</p>
        </div></UICard>
        <UICard><div className="p-3 text-center">
          <DollarSign className="h-4 w-4 text-amber-400 mx-auto mb-1" />
          <p className="text-lg font-bold text-slate-100">R{commissions.filter(c => c.status === "PENDING").reduce((s, c) => s + c.amount_zar, 0).toLocaleString()}</p>
          <p className="text-[10px] text-slate-400">Pending Comm</p>
        </div></UICard>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <UIInput placeholder="Search leads, contacts..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
      </div>

      {/* Leads list */}
      <div className="space-y-2">
        <div className="flex justify-between items-center">
          <p className="text-xs text-slate-400">{filteredLeads.length} new leads</p>
          <UIButton size="sm" onClick={() => setShowNewLead(true)}><Plus className="mr-1 h-3 w-3" /> New Lead</UIButton>
        </div>
        {loading ? (
          <p className="text-xs text-slate-400 text-center py-8">Loading...</p>
        ) : (
          <>
            {filteredLeads.map(l => (
              <LeadCard key={l.id} lead={l} onConvert={setConvertLead} onView={lead => handleViewContact(lead.id)} />
            ))}
            {filteredLeads.length === 0 && <p className="text-xs text-slate-400 text-center py-8">No new leads</p>}
          </>
        )}
      </div>

      {/* New Lead Dialog */}
      <UIDialog open={showNewLead} onClose={() => setShowNewLead(false)} title="New Lead">
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div><UILabel>First Name *</UILabel><UIInput value={newLead.first_name} onChange={e => setNewLead({ ...newLead, first_name: e.target.value })} className="mt-1" /></div>
            <div><UILabel>Last Name</UILabel><UIInput value={newLead.last_name} onChange={e => setNewLead({ ...newLead, last_name: e.target.value })} className="mt-1" /></div>
          </div>
          <div><UILabel>Phone</UILabel><UIInput value={newLead.phone} onChange={e => setNewLead({ ...newLead, phone: e.target.value })} className="mt-1" /></div>
          <div><UILabel>Email</UILabel><UIInput value={newLead.email} onChange={e => setNewLead({ ...newLead, email: e.target.value })} className="mt-1" /></div>
          <div><UILabel>Address</UILabel><UIInput value={newLead.address} onChange={e => setNewLead({ ...newLead, address: e.target.value })} className="mt-1" /></div>
          <UIButton className="w-full" onClick={handleCreateLead} disabled={!newLead.first_name}>Create Lead</UIButton>
        </div>
      </UIDialog>

      {/* Convert Lead Dialog */}
      <UIDialog open={!!convertLead} onClose={() => setConvertLead(null)} title="Convert Lead to Deal">
        {convertLead && (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">Convert <strong className="text-slate-100">{convertLead.first_name} {convertLead.last_name}</strong> into a deal?</p>
            <UIButton className="w-full" onClick={() => handleConvert(convertLead)}>Create Deal</UIButton>
          </div>
        )}
      </UIDialog>

      {/* Quote Builder Dialog */}
      <UIDialog open={!!quoteContactId} onClose={() => setQuoteContactId(null)} title="Build Quote">
        {quoteContactId && <QuoteBuilder customerId={quoteContactId} onDone={() => { setQuoteContactId(null); load(); }} />}
      </UIDialog>
    </div>
  );
}
