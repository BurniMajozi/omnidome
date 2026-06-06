"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Search, Phone, Mail, ChevronRight, FileText, ArrowLeft, Send, X,
} from "lucide-react";
import { fieldSalesApi } from "@/lib/api/client";
import type {
  MobileContact, MobileDeal, Customer360, MobileCommission,
} from "@/lib/api/types";

/* ─── Inline UI primitives ──────────────────────────────────────────── */

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

function UIInput({ value, onChange, placeholder, className = "" }: {
  value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; placeholder?: string; className?: string;
}) {
  return (
    <input
      value={value}
      onChange={e}
      placeholder={placeholder}
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
      <div className="w-full max-w-md max-h-[80vh] overflow-y-auto bg-[#1e293b] border border-[#334155] rounded-2xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
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
        <label className="text-xs text-slate-400">Term</label>
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

/* ─── Customers Tab ─────────────────────────────────────────────────── */

export default function CustomersTab() {
  const [contacts, setContacts] = useState<MobileContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedContact, setSelectedContact] = useState<Customer360 | null>(null);
  const [quoteContactId, setQuoteContactId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const c = await fieldSalesApi.listContacts({ limit: 50 });
      setContacts(c);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleViewContact = async (contactId: string) => {
    try {
      const data = await fieldSalesApi.getCustomer360(contactId);
      setSelectedContact(data);
    } catch { /* fallback */ }
  };

  const filteredContacts = contacts.filter(c => `${c.first_name} ${c.last_name} ${c.phone}`.toLowerCase().includes(search.toLowerCase()));

  if (selectedContact) {
    return <Customer360Panel contact={selectedContact} onClose={() => setSelectedContact(null)} />;
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <UIInput placeholder="Search contacts..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
      </div>

      {/* Contact list */}
      <p className="text-xs text-slate-400">{filteredContacts.length} contacts</p>
      {loading ? (
        <p className="text-xs text-slate-400 text-center py-8">Loading...</p>
      ) : (
        <div className="space-y-2">
          {filteredContacts.map(c => (
            <UICard key={c.id} onClick={() => handleViewContact(c.id)}>
              <div className="p-3 flex items-center justify-between">
                <div>
                  <p className="font-medium text-sm text-slate-100">{c.first_name} {c.last_name}</p>
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    {c.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{c.phone}</span>}
                    {c.rica_verified && <UIBadge className="text-[10px] bg-emerald-500/20 text-emerald-400">RICA ✓</UIBadge>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <UIButton variant="ghost" size="icon" onClick={e => { e.stopPropagation(); setQuoteContactId(c.id); }}>
                    <FileText className="h-3.5 w-3.5 text-violet-400" />
                  </UIButton>
                  <ChevronRight className="h-4 w-4 text-slate-400 self-center" />
                </div>
              </div>
            </UICard>
          ))}
          {filteredContacts.length === 0 && !loading && (
            <p className="text-xs text-slate-400 text-center py-8">No contacts found</p>
          )}
        </div>
      )}

      {/* Quote Builder Dialog */}
      <UIDialog open={!!quoteContactId} onClose={() => setQuoteContactId(null)} title="Build Quote">
        {quoteContactId && <QuoteBuilder customerId={quoteContactId} onDone={() => { setQuoteContactId(null); load(); }} />}
      </UIDialog>
    </div>
  );
}
