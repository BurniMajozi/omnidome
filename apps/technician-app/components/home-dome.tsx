"use client";
import RoomHome, { type Room } from "./room-home";
import HomeReports, { ReportingRequests } from "./home-reports";
import themeStyles from "./home-dome-theme.module.css";
import HomeFeatures from "./home-features";
import IntegrationGallery from "./integration-gallery";
import IntegrationSetup, { IntegrationDevices, type SetupTarget } from "./integration-setup";
import EnergyDashboard from "./energy-dashboard";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Home, Lightbulb, Camera, Activity, Plug, ShieldCheck, Zap, RefreshCw, ExternalLink } from "lucide-react";

type Requester = (path: string, init?: RequestInit) => Promise<Response>;
type HomeRow = { id: string; name: string; customer_id: string; is_owner: boolean; status: string; last_sync_at: string | null; last_error: string | null; dashboard_url: string | null; managed_gateway: boolean };
type Device = { id: string; name: string; domain: string; room: string | null; state: string; attributes: Record<string, string | number>; observed_at: string };
type Grant = { id: string; staff_name: string; reason: string; reference: string; scopes: string[]; status: string; expires_at: string };
type Integration = { id: string; name: string; category: string; status: string; requirement: string; docs_url: string; guided?: boolean };
type Energy = { totals: Record<string, { value: number | null; unit: string; reason: string | null }>; power: Record<string, { time: string; kw: number }[]>; grid_cost_zar: number | null; note: string; flows?: Record<string, boolean> };
type Choice = { id: string; label: string };
const root = "/api/iot/homes";
const scopes = ["diagnostics", "control", "camera"];
const sourceNames: Record<string, string> = { grid_import: "Grid import", grid_export: "Grid export", solar: "Solar production", battery_charge: "Battery charge", battery_discharge: "Battery discharge", gas: "Gas", water: "Water", grid_power: "Grid power", solar_power: "Solar power", battery_power: "Battery power", home_power: "Home power" };
const pretty = (value: string | null) => value ? new Date(value).toLocaleString("en-ZA", { timeZone: "Africa/Johannesburg" }) : "Not yet synced";
const button = "rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-50";
const input = "w-full rounded-lg border border-gray-300 bg-white p-2 text-gray-900";
const card = "rounded-2xl border border-gray-200 bg-white p-5";
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Johannesburg" }).format(new Date());

export default function HomeDome({ request, customers = [], users = [], theme = "light" }: { request: Requester; customers?: Choice[]; users?: Choice[]; theme?: "light" | "dark" }) {
  const [homes, setHomes] = useState<HomeRow[]>([]);
  const [selected, setSelected] = useState("");
  const [tab, setTab] = useState("Home");
  const [rooms, setRooms] = useState<Room[]>([]);
  const [devices, setDevices] = useState<Device[]>([]);
  const [grants, setGrants] = useState<Grant[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [audit, setAudit] = useState<{ action: string; created_at: string }[]>([]);
  const [caps, setCaps] = useState({ can_provision: false, can_request_support: false, can_assign_gateway: false, gateway_onboarding_url: null as string | null });
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const home = homes.find(row => row.id === selected);
  const active = grants.filter(row => row.status === "approved" && Date.parse(row.expires_at) > Date.now());
  const allowed = (scope: string) => Boolean(home?.is_owner || active.some(row => row.scopes.includes(scope)));
  const canRead = allowed("diagnostics");

  const call = useCallback(async <T,>(path: string, init?: RequestInit): Promise<T> => {
    const response = await request(root + path, { cache: "no-store", ...init });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === "string" ? data.detail : data.detail?.message || `Request failed (${response.status})`);
    }
    return response.json();
  }, [request]);
  const refresh = useCallback(async () => {
    const rows = await call<HomeRow[]>("");
    setHomes(rows);
    setSelected(current => rows.some(row => row.id === current) ? current : rows[0]?.id || "");
  }, [call]);
  useEffect(() => {
    let alive = true;
    void Promise.all([call<HomeRow[]>(""), call<typeof caps>("/capabilities")]).then(([rows, capabilities]) => {
      if (alive) { setHomes(rows); setSelected(rows[0]?.id || ""); setCaps(capabilities); }
    }).catch(err => { if (alive) setError(err.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [call]);
  const details = useCallback(async () => {
    if (!selected) return;
    const id = selected;
    const support = await call<Grant[]>(`/${id}/support`);
    if (selectedRef.current !== id) return;
    setGrants(support);
    const owner = homes.find(row => row.id === id)?.is_owner;
    if (!owner && !support.some(row => row.status === "approved" && Date.parse(row.expires_at) > Date.now() && row.scopes.includes("diagnostics"))) {
      setDevices([]); setRooms([]); setIntegrations([]); return;
    }
    const [rows, catalogue, roomRows] = await Promise.all([call<Device[]>(`/${id}/devices`), call<Integration[]>(`/${id}/integrations`), call<Room[]>(`/${id}/rooms`)]);
    if (selectedRef.current === id) { setDevices(rows); setRooms(roomRows); setIntegrations(catalogue); }
    if (owner) {
      const events = await call<typeof audit>(`/${id}/audit`);
      if (selectedRef.current === id) setAudit(events);
    }
  }, [selected, homes, call]);
  useEffect(() => {
    setDevices([]); setRooms([]); setGrants([]); setIntegrations([]); setAudit([]); setTab("Home"); setNotice("");
  }, [selected]);
  useEffect(() => {
    if (!selected) return;
    const load = () => { void details().catch(err => setError(err.message)); };
    load();
    const timer = setInterval(load, 15000);
    return () => clearInterval(timer);
  }, [selected, details]);
  const act = async (path: string, method: string, data?: unknown) => {
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await call<{ ok?: boolean; message?: string }>(path, { method, headers: { "Content-Type": "application/json" }, body: data === undefined ? undefined : JSON.stringify(data) });
      if (result.ok === false) throw new Error(result.message || "Action could not be completed");
      setNotice(result.message || "Saved"); await refresh(); await details();
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  };
  const [provisionOpen, setProvisionOpen] = useState(false);
  const [requestsOpen, setRequestsOpen] = useState(false);
  const [newHome, setNewHome] = useState({ name: "", customer_id: "", owner_user_id: "" });
  const [connection, setConnection] = useState({ ha_url: "", ha_token: "" });
  const [reason, setReason] = useState("");
  const [reference, setReference] = useState("");
  const [requested, setRequested] = useState(["diagnostics"]);
  const [setup, setSetup] = useState<SetupTarget | null>(null);

  return <section className={themeStyles.surface + " " + (theme === "dark" ? themeStyles.dark : "") + " space-y-5 rounded-2xl p-4 md:p-6"}>
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 className="flex items-center gap-2 text-2xl font-semibold"><Home className="text-cyan-600" />HomeDome</h2><p className="mt-1 text-sm text-gray-600">Your connected home, with support you control.</p></div>
      <div className="flex gap-2"><button className={button} disabled={busy} onClick={() => void refresh().catch(err => setError(err.message))}><RefreshCw className="inline h-4 w-4" /> Refresh</button>
        {caps.can_provision && customers.length > 0 && users.length > 0 && <button className={button} onClick={() => setProvisionOpen(!provisionOpen)}>Add customer home</button>}</div>
    </header>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {notice && <p role="status" className="rounded-lg bg-cyan-50 p-3 text-sm text-cyan-900">{notice}</p>}
    {caps.can_provision && <div><button className={button} aria-expanded={requestsOpen} onClick={() => setRequestsOpen(!requestsOpen)}>{requestsOpen ? "Hide reporting requests" : "Manage reporting upgrades"}</button>{requestsOpen && <div className="mt-4"><ReportingRequests call={call} /></div>}</div>}
    {provisionOpen && <form className={card + " grid gap-3 md:grid-cols-3"} onSubmit={event => { event.preventDefault(); void act("", "POST", newHome); }}>
      <label>Home name<input required className={input} value={newHome.name} onChange={e => setNewHome({ ...newHome, name: e.target.value })} /></label>
      <label>Customer<select required className={input} value={newHome.customer_id} onChange={e => setNewHome({ ...newHome, customer_id: e.target.value })}><option value="">Select customer</option>{customers.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
      <label>Customer login<select required className={input} value={newHome.owner_user_id} onChange={e => setNewHome({ ...newHome, owner_user_id: e.target.value })}><option value="">Select verified user</option>{users.map(row => <option key={row.id} value={row.id}>{row.label}</option>)}</select></label>
      <p className="text-sm text-gray-600 md:col-span-3">This user will own the home and approve support access. Confirm the customer identity before saving.</p><button className={button} disabled={busy}>Create home</button>
    </form>}
    {loading ? <p role="status">Loading HomeDome…</p> : homes.length === 0 ? <div className={card}><Home className="mb-3 h-10 w-10 text-cyan-600" /><h3 className="font-semibold">Your home starts here</h3><p className="mt-2 text-sm text-gray-600">Your ISP needs to assign your property to your verified login. You can then connect Home Assistant, add devices and choose who may help.</p></div> : <>
      <select aria-label="Choose home" className={input + " max-w-md"} value={selected} onChange={e => setSelected(e.target.value)}>{homes.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select>
      {caps.can_assign_gateway && !home?.managed_gateway && <button className={button} disabled={busy} onClick={() => { if (window.confirm("Assign the pilot gateway to this customer home? It cannot be shared with another home.")) void act(`/${selected}/gateway`, "POST"); }}>Use prepared gateway for this home</button>}
      <div className="flex flex-wrap items-center gap-3 text-sm"><span className="rounded-full bg-gray-200 px-3 py-1">{home?.status}</span><span className="text-gray-600">Last sync: {pretty(home?.last_sync_at || null)}</span>
        {canRead && <button disabled={busy} className={button} onClick={() => void act(`/${selected}/sync`, "POST")}>Sync devices</button>}
      </div>
      {home?.status !== "connected" && <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><p>Connect your gateway to bring its rooms, devices and readings into HomeDome. Any existing readings are historical.</p>{home?.is_owner && <button className={button + " mt-2"} onClick={() => setTab("Connection")}>Connect your home</button>}</div>}
      <nav aria-label="HomeDome sections" className="flex gap-1 overflow-x-auto border-b">{["Home", "Energy", "Reports", "Integrations", "Support", ...(home?.is_owner ? ["Media", "Map", "To-do", "Connection", "Activity"] : [])].map(name => <button key={name} className={"whitespace-nowrap border-b-2 px-4 py-3 text-sm " + (tab === name ? "border-cyan-600 font-semibold text-cyan-700" : "border-transparent text-gray-600")} onClick={() => setTab(name)}>{name}</button>)}</nav>
      {tab === "Reports" && (canRead ? <HomeReports key={selected} homeId={selected} owner={Boolean(home?.is_owner)} call={call} /> : <p className={card}>Customer-approved diagnostics access is required to view household reports. Open Support to request access. Commercial upgrade requests can be managed separately.</p>)}
      {tab === "Home" && (canRead ? <RoomHome key={selected} homeId={selected} devices={devices} rooms={rooms} owner={Boolean(home?.is_owner)} connected={home?.status === "connected"} control={allowed("control")} camera={allowed("camera")} busy={busy} call={call} changed={details} openMedia={() => setTab("Media")} cameraPreview={row => <CameraPreview request={request} path={root + `/${selected}/devices/${row.id}/snapshot`} allowed={allowed("camera")} />} /> : <p className={card}>Device diagnostics require the customer's approval. Open Support to request access.</p>)}
      {home?.is_owner && ["Media", "Map", "To-do"].includes(tab) && <HomeFeatures key={selected + tab} kind={tab as "Media" | "Map" | "To-do"} homeId={selected} call={call} />}
      {tab === "Energy" && (canRead ? <EnergyView key={selected} homeId={selected} owner={Boolean(home?.is_owner)} devices={devices} call={call} /> : <p className={card}>Customer-approved diagnostics access is required.</p>)}
      {tab === "Integrations" && (canRead ? <>{setup && home?.is_owner && home.status === "connected" && <IntegrationSetup key={selected + setup.id} homeId={selected} target={setup} call={call} request={request} onClose={() => setSetup(null)} onDone={details} />}{setup && home?.is_owner && home.status !== "connected" && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">Connect your home gateway first (Connection tab). HomeDome sets up devices through your Home Assistant.</p>}{!setup && integrations.filter(row => row.guided && row.status === "loaded").map(row => <details key={row.id} className={card + " mb-4"}><summary className="cursor-pointer font-semibold">{row.name} devices</summary><div className="mt-3"><IntegrationDevices homeId={selected} domain={row.id} call={call} request={request} /></div></details>)}<IntegrationGallery key={selected} rows={integrations} onSetup={home?.is_owner ? row => setSetup({ id: row.id, name: row.name }) : undefined} /></> : <p className={card}>Customer-approved diagnostics access is required.</p>)}
      {tab === "Support" && <div className="space-y-3"><div className={card}><ShieldCheck className="mb-2 text-cyan-600" /><h3 className="font-semibold">You're in control</h3><p className="mt-2 text-sm text-gray-600">Support requests expire after 24 hours. Approved access lasts up to one hour and can be revoked at any time. Camera access is separate from device control.</p></div>
        {!home?.is_owner && caps.can_request_support && <form className={card + " space-y-3"} onSubmit={e => { e.preventDefault(); void act(`/${selected}/support`, "POST", { reason, reference, scopes: requested }); }}><label className="block">Ticket or job reference<input required className={input} value={reference} onChange={e => setReference(e.target.value)} /></label><label className="block">What do you need to help with?<textarea required minLength={5} className={input} value={reason} onChange={e => setReason(e.target.value)} /></label><ScopeChoices value={requested} change={setRequested} /><button disabled={busy || !requested.length} className={button}>Request customer approval</button></form>}
        {!grants.length && <p className={card}>No support sessions for this home.</p>}
        {grants.map(row => <GrantCard key={row.id} row={row} owner={Boolean(home?.is_owner)} busy={busy} act={(method, data) => act(`/${selected}/support/${row.id}${method === "POST" ? "/approve" : ""}`, method, data)} />)}
      </div>}
      {tab === "Connection" && home?.is_owner && <form className={card + " max-w-xl space-y-3"} onSubmit={e => { e.preventDefault(); const payload = { ...connection, ha_url: home.managed_gateway ? "http://localhost:8123" : connection.ha_url }; setConnection({ ...connection, ha_token: "" }); void act(`/${selected}/connection`, "POST", payload); }}>
        <h3 className="font-semibold">Connect Home Assistant</h3><p className="text-sm text-gray-600">Use your Home Assistant address and a dedicated access token. Tokens are encrypted on the server and are never returned to this app. Your ISP must configure a permitted secure connection to your home.</p>
        {home.managed_gateway && <p className="text-sm">Your gateway address is preconfigured below. Complete gateway onboarding separately, then enter its owner access token here.</p>}
        <label className="block">Home Assistant URL<input className={input} required type="url" autoComplete="off" placeholder="https://your-home.example.com" readOnly={home.managed_gateway} value={home.managed_gateway ? "http://localhost:8123" : connection.ha_url} onChange={e => setConnection({ ...connection, ha_url: e.target.value })} /></label>
        <label className="block">Access token<input className={input} required type="password" autoComplete="new-password" value={connection.ha_token} onChange={e => setConnection({ ...connection, ha_token: e.target.value })} /></label>
        <button className={button} disabled={busy}>Connect and sync</button><button type="button" className={button + " ml-2"} disabled={busy} onClick={() => { if (confirm("Disconnect Home Assistant and revoke all support access?")) void act(`/${selected}/connection`, "DELETE"); }}>Disconnect</button>
      </form>}
      {tab === "Activity" && <div className={card}><h3 className="mb-3 font-semibold">Access and activity trail</h3>{audit.map((row, index) => <p key={index} className="border-b py-2 text-sm">{row.action.replaceAll("_", " ")} <span className="text-gray-500">· {pretty(row.created_at)}</span></p>)}</div>}
    </>}
  </section>;
}

function ScopeChoices({ value, change, choices = scopes }: { value: string[]; change: (value: string[]) => void; choices?: string[] }) {
  return <div className="flex flex-wrap gap-3">{choices.map(scope => <label className="flex items-center gap-2 text-sm" key={scope}><input type="checkbox" disabled={scope === "diagnostics"} checked={value.includes(scope)} onChange={e => change(e.target.checked ? [...value, scope] : value.filter(item => item !== scope))} />{scope === "camera" ? "View cameras" : scope === "control" ? "Control devices" : "Device diagnostics (required)"}</label>)}</div>;
}
function GrantCard({ row, owner, busy, act }: { row: Grant; owner: boolean; busy: boolean; act: (method: string, data?: unknown) => Promise<void> }) {
  const [chosen, setChosen] = useState(row.scopes);
  const [minutes, setMinutes] = useState(30);
  return <div className={card}><h4 className="font-semibold">{row.staff_name || "Support staff"} · {row.status}</h4><p className="my-2 text-sm">{row.reason}</p><p className="mb-3 text-xs text-gray-500">{row.reference} · Expires {pretty(row.expires_at)}</p>
    {row.status === "pending" && owner && <><ScopeChoices value={chosen} change={setChosen} choices={row.scopes} /><label className="my-3 block text-sm">Access duration <select className="ml-2 rounded border p-2" value={minutes} onChange={e => setMinutes(Number(e.target.value))}>{[5, 15, 30, 60].map(value => <option key={value} value={value}>{value} minutes</option>)}</select></label><button disabled={busy || !chosen.length} className={button} onClick={() => void act("POST", { scopes: chosen, minutes })}>Approve selected access</button></>}
    {["approved", "pending"].includes(row.status) && <button disabled={busy} className={button + " ml-2"} onClick={() => void act("DELETE")}>{row.status === "pending" && owner ? "Decline" : "End access"}</button>}
  </div>;
}
function CameraPreview({ request, path, allowed }: { request: Requester; path: string; allowed: boolean }) {
  const [url, setUrl] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (!allowed) setUrl(""); }, [allowed]);
  useEffect(() => { if (!url) return; const timer = setTimeout(() => setUrl(""), 30000); return () => { clearTimeout(timer); URL.revokeObjectURL(url); }; }, [url]);
  const view = async () => { setBusy(true); setError(""); try { const res = await request(path, { cache: "no-store" }); if (!res.ok) throw new Error("Camera access expired or the camera is unavailable"); setUrl(URL.createObjectURL(await res.blob())); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  return <div className="mt-3"><button className={button} disabled={busy || !allowed} onClick={() => void view()}>View current snapshot</button>{url && <img className="mt-3 w-full rounded-lg" alt="Current camera snapshot" src={url} />}{error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}</div>;
}
function EnergyView({ homeId, owner, devices, call }: { homeId: string; owner: boolean; devices: Device[]; call: <T>(path: string, init?: RequestInit) => Promise<T> }) {
  const [day, setDay] = useState(today()); const [report, setReport] = useState<Energy | null>(null); const [error, setError] = useState("");
  const [editing, setEditing] = useState(false); const [meters, setMeters] = useState<Record<string, string>>({}); const [tariff, setTariff] = useState("");
  const refresh = useCallback(() => { setError(""); void call<Energy>(`/${homeId}/energy?day=${day}`).then(setReport).catch(e => setError(e.message)); }, [call, homeId, day]);
  useEffect(() => { refresh(); const timer = setInterval(refresh, 30000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => { if (owner) void call<{ meters: Record<string, string>; grid_tariff: number | null }>(`/${homeId}/energy/config`).then(data => { setMeters(data.meters); setTariff(data.grid_tariff === null ? "" : String(data.grid_tariff)); }).catch(e => setError(e.message)); }, [owner, homeId, call]);
  const save = async () => { try { await call(`/${homeId}/energy/config`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ meters: Object.fromEntries(Object.entries(meters).filter(([, id]) => id)), grid_tariff: tariff === "" ? null : Number(tariff) }) }); setEditing(false); setError(""); refresh(); } catch (e) { setError((e as Error).message); } };
  return <div className="space-y-4"><div className="flex flex-wrap items-center gap-3"><Zap className="text-cyan-600" /><h3 className="text-lg font-semibold">Energy</h3><input aria-label="Energy report date" className="rounded-lg border p-2" type="date" value={day} onChange={e => { setReport(null); setDay(e.target.value); }} />{owner && <button className={button} onClick={() => setEditing(!editing)}>Choose meters</button>}<button className={button} onClick={refresh}>Refresh report</button></div>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {editing && <form className={card + " grid gap-3 sm:grid-cols-2"} onSubmit={e => { e.preventDefault(); void save(); }}>{Object.entries(sourceNames).map(([source, label]) => <label key={source} className="text-sm">{label}<select className={input} value={meters[source] || ""} onChange={e => setMeters({ ...meters, [source]: e.target.value })}><option value="">Not connected</option>{devices.filter(row => row.domain === "sensor").map(row => <option key={row.id} value={row.id}>{row.name} ({row.attributes.unit_of_measurement || "no unit"})</option>)}</select></label>)}<label className="text-sm">Grid tariff (R/kWh, optional)<input className={input} type="number" min="0" max="1000" step="0.01" value={tariff} onChange={e => setTariff(e.target.value)} /></label><button className={button}>Save meters</button></form>}
    <EnergyDashboard report={report} day={day} onDayChange={value => { setReport(null); setDay(value); }} />
  </div>;
}


