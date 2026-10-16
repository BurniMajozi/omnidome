"use client";
import React, { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Camera, CheckCircle2, ExternalLink, Loader2, RefreshCw } from "lucide-react";

type Call = <T>(path: string, init?: RequestInit) => Promise<T>;
type Requester = (path: string, init?: RequestInit) => Promise<Response>;
type Option = { value: string; label: string };
type Field = { name: string; type: string; required: boolean; default?: string | number | boolean; options?: Option[] };
type Step = { type: string; flow_id: string; step_id: string; reason: string; title: string; errors: Record<string, string>; fields: Field[]; menu_options: string[] };
type Entity = { id: string; name: string; domain: string; state: string; attributes: Record<string, string | number>; ptz: string | null };
export type SetupTarget = { id: string; name: string };

const button = "rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-50";
const primary = "rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50";
const input = "w-full rounded-lg border border-gray-300 bg-white p-2 text-gray-900";
const card = "rounded-2xl border border-gray-200 bg-white p-5";
const json = { "Content-Type": "application/json" };

// What Home Assistant's Imou page documents, shown in HomeDome's own words.
const IMOU = {
  openPlatform: "https://open.imoulife.com",
  prerequisites: [
    "Register or sign in at the Imou Open Platform and open the Control board.",
    "Under App Information, copy your App ID and App secret.",
    "Add your cameras in the Imou app or Open Platform so they appear on that account.",
  ],
  labels: { app_id: "App ID", appid: "App ID", app_secret: "App secret", appsecret: "App secret", region: "Server region", server_region: "Server region" } as Record<string, string>,
  regions: { sg: "Singapore (Asia-Pacific)", eu: "Europe", na: "North America", cn: "China" } as Record<string, string>,
  help: { "App ID": "From your Imou Open Platform application.", "App secret": "From the same application. Stored only in your Home Assistant.", "Server region": "Choose the region your Open Platform account was registered in." } as Record<string, string>,
  provides: [
    ["Cameras", "Live view SD and HD for each channel, shown as snapshots in HomeDome."],
    ["Camera movement", "PTZ up, down, left and right, on cameras that support it."],
    ["Switches and selects", "Device settings such as night vision mode and volume, where the camera reports them."],
    ["Sensors", "Battery, storage used, online status and, on sockets, power and energy."],
  ],
  errors: {
    invalid_auth: "Imou rejected the App ID or App secret. Check them and the server region against your Open Platform application.",
    cannot_connect: "Home Assistant could not reach the Imou cloud. Check the gateway's internet connection and try again.",
    unknown: "Something unexpected happened while contacting Imou. Try again.",
  } as Record<string, string>,
};
const GUIDES: Record<string, { title: string; steps: string[]; prerequisites: string[]; link: string; docs: string; intro: string }> = {
  imou: { title: "Imou cameras", steps: ["Prepare", "Account details", "Your devices"], prerequisites: IMOU.prerequisites, link: IMOU.openPlatform, docs: "https://www.home-assistant.io/integrations/imou/", intro: "HomeDome connects your Imou Open Platform account to your home gateway. Cloud API limits apply: each App ID includes 30,000 free requests a month, and usage above that is billed by Imou." },
  onvif: { title: "ONVIF cameras", steps: ["Prepare", "Camera details", "Your devices"], link: "https://www.home-assistant.io/integrations/onvif/", docs: "https://www.home-assistant.io/integrations/onvif/", intro: "Connect a camera that supports ONVIF over your local network.", prerequisites: ["Enable ONVIF on the camera and create a camera user.", "Note the camera's IP address, ONVIF port and credentials.", "Make sure the gateway can reach the camera on the home network."] },
};
const titleCase = (value: string) => value.replace(/_/g, " ").replace(/^./, char => char.toUpperCase());
const secret = (name: string) => /secret|password|token|key/i.test(name);

export default function IntegrationSetup({ homeId, target, call, request, onClose, onDone }: { homeId: string; target: SetupTarget; call: Call; request: Requester; onClose: () => void; onDone: () => void | Promise<void> }) {
  const guide = GUIDES[target.id] || GUIDES.imou;
  const [stage, setStage] = useState(0);
  const [ready, setReady] = useState<boolean[]>(guide.prerequisites.map(() => false));
  const [step, setStep] = useState<Step | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/${homeId}/integrations`;

  const apply = (next: Step) => {
    setStep(next);
    if (next.type === "form") setValues(Object.fromEntries(next.fields.map(f => [f.name, f.default !== undefined ? String(f.default) : f.options?.[0]?.value ?? ""])));
    if (next.type === "create_entry") { setStage(2); void onDone(); }
    if (next.type === "abort") setError(abortText(next.reason));
  };
  const abortText = (reason: string) => reason === "already_configured" ? "This account is already set up on your gateway." : reason === "invalid_auth" ? IMOU.errors.invalid_auth : `Home Assistant ended the setup (${reason.replace(/_/g, " ") || "unknown reason"}).`;
  const run = async (task: () => Promise<void>) => { setBusy(true); setError(""); try { await task(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } };
  const begin = () => run(async () => { apply(await call<Step>(`${path}/${target.id}/setup`, { method: "POST" })); setStage(1); });
  const submit = (data: Record<string, string>) => run(async () => { if (step) apply(await call<Step>(`${path}/setup/${step.flow_id}`, { method: "POST", headers: json, body: JSON.stringify({ user_input: data }) })); });
  const close = () => { if (step && step.type !== "create_entry") void call(`${path}/setup/${step.flow_id}`, { method: "DELETE" }).catch(() => undefined); onClose(); };
  const problem = step?.errors.base ? IMOU.errors[step.errors.base] || titleCase(step.errors.base) : "";

  return <div className={card + " space-y-5"} role="dialog" aria-label={`Set up ${guide.title}`}>
    <div className="flex items-start justify-between gap-3"><div><h3 className="text-xl font-semibold">Set up {guide.title}</h3><p className="mt-1 text-sm text-gray-600">{guide.intro}</p></div><button className={button} onClick={close}>Close</button></div>
    <ol className="flex flex-wrap gap-2 text-sm" aria-label="Setup progress">{guide.steps.map((name, i) => <li key={name} aria-current={i === stage ? "step" : undefined} className={"flex items-center gap-2 rounded-full px-3 py-1 " + (i === stage ? "bg-cyan-600 text-white" : i < stage ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-600")}><span className="font-semibold">{i < stage ? "✓" : i + 1}</span>{name}</li>)}</ol>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

    {stage === 0 && <div className="space-y-4">
      <p className="text-sm font-medium">Before you start, confirm each item:</p>
      <ul className="space-y-2">{guide.prerequisites.map((text, i) => <li key={text}><label className="flex items-start gap-3 text-sm"><input type="checkbox" className="mt-1" checked={ready[i]} onChange={e => setReady(ready.map((v, j) => j === i ? e.target.checked : v))} />{text}</label></li>)}</ul>
      <div className="flex flex-wrap gap-2"><a className={button} href={guide.link} target="_blank" rel="noopener noreferrer">Open {target.id === "imou" ? "Imou Open Platform" : "setup guide"} <ExternalLink className="inline h-4 w-4" /></a>
        <button className={primary} disabled={busy || !ready.every(Boolean)} onClick={() => void begin()}>{busy ? "Starting…" : "Continue"}</button></div>
      {target.id === "imou" && <div className="grid gap-2 sm:grid-cols-2">{IMOU.provides.map(([name, text]) => <div key={name} className="rounded-xl bg-gray-50 p-3 text-sm"><p className="font-medium">{name}</p><p className="mt-1 text-gray-600">{text}</p></div>)}</div>}
      <p className="text-xs text-gray-500">Device commands travel through Imou's servers. Review Imou's privacy policy before continuing.</p>
    </div>}

    {stage === 1 && step?.type === "form" && <form className="max-w-xl space-y-4" onSubmit={e => { e.preventDefault(); const data = values; setValues(Object.fromEntries(Object.entries(values).map(([k, v]) => [k, secret(k) ? "" : v]))); void submit(data); }}>
      {problem && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{problem}</p>}
      {step.fields.map(field => <label key={field.name} className="block text-sm"><span className="font-medium">{(target.id === "imou" && IMOU.labels[field.name]) || titleCase(field.name)}{field.required && " *"}</span>
        {field.options ? <select required={field.required} className={input} value={values[field.name] ?? ""} onChange={e => setValues({ ...values, [field.name]: e.target.value })}>{field.options.map(o => <option key={o.value} value={o.value}>{(target.id === "imou" && IMOU.regions[o.value]) || o.label}</option>)}</select>
          : field.type === "boolean" ? <input type="checkbox" className="ml-2" checked={values[field.name] === "true"} onChange={e => setValues({ ...values, [field.name]: String(e.target.checked) })} />
          : <input required={field.required} className={input} type={secret(field.name) ? "password" : field.type === "integer" || field.type === "float" ? "number" : "text"} autoComplete="off" value={values[field.name] ?? ""} onChange={e => setValues({ ...values, [field.name]: e.target.value })} />}
        {target.id === "imou" && IMOU.help[IMOU.labels[field.name]] && <span className="mt-1 block text-xs text-gray-500">{IMOU.help[IMOU.labels[field.name]]}</span>}</label>)}
      <div className="flex gap-2"><button className={primary} disabled={busy}>{busy ? <><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />Connecting…</> : "Connect and find devices"}</button><button type="button" className={button} disabled={busy} onClick={close}>Cancel</button></div>
      <p className="text-xs text-gray-500">Your details go straight to your own Home Assistant. HomeDome does not keep them.</p>
    </form>}
    {stage === 1 && step && step.type !== "form" && step.type !== "abort" && <p className="text-sm text-gray-600">Home Assistant needs a step HomeDome cannot show yet ({step.step_id || step.type}). Finish it in your Home Assistant dashboard.</p>}
    {stage === 1 && step?.type === "abort" && <button className={button} onClick={() => { setStep(null); setStage(0); setError(""); }}>Start again</button>}

    {stage === 2 && <div className="space-y-4"><p className="flex items-center gap-2 font-medium text-emerald-700"><CheckCircle2 className="h-5 w-5" />{step?.title || guide.title} is connected.</p>
      <IntegrationDevices homeId={homeId} domain={target.id} call={call} request={request} /></div>}
  </div>;
}

export function IntegrationDevices({ homeId, domain, call, request }: { homeId: string; domain: string; call: Call; request: Requester }) {
  const [rows, setRows] = useState<Entity[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (resync: boolean) => {
    setBusy(true); setError("");
    try {
      if (resync) await call(`/${homeId}/sync`, { method: "POST" });
      setRows((await call<{ entities: Entity[] }>(`/${homeId}/integrations/${domain}/entities`)).entities);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }, [call, homeId, domain]);
  useEffect(() => { void load(false); }, [load]);
  // Imou's first cloud refresh can lag setup by a minute; look again a couple of times.
  useEffect(() => { if (rows && rows.length === 0) { const t = setTimeout(() => void load(true), 20000); return () => clearTimeout(t); } }, [rows, load]);
  const by = (name: string) => (rows || []).filter(r => r.domain === name);
  const cameras = by("camera");
  return <div className="space-y-4">
    <div className="flex items-center justify-between"><h4 className="font-semibold">Devices found</h4><button className={button} disabled={busy} onClick={() => void load(true)}><RefreshCw className="mr-1 inline h-4 w-4" />Look for devices</button></div>
    {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
    {rows === null && <p role="status" className="text-sm text-gray-600">Looking for devices…</p>}
    {rows && rows.length === 0 && <p role="status" className="rounded-lg bg-gray-50 p-3 text-sm text-gray-600">No devices yet. Imou refreshes your device list every 2 minutes. If nothing appears, check the cameras are added to the account and online in the Imou app.</p>}
    {cameras.length > 0 && <div className="grid gap-3 md:grid-cols-2">{cameras.map(cam => <CameraCard key={cam.id} cam={cam} homeId={homeId} request={request} call={call} ptz={by("button").filter(b => b.ptz && b.name.toLowerCase().startsWith(cam.name.toLowerCase().replace(/\s*live view.*$/i, "")))} />)}</div>}
    {(["switch", "select", "sensor", "binary_sensor"] as const).map(kind => by(kind).length > 0 && <div key={kind}><p className="mb-2 text-sm font-medium">{{ switch: "Switches", select: "Selects", sensor: "Sensors", binary_sensor: "Binary sensors" }[kind]}</p>
      <div className="flex flex-wrap gap-2">{by(kind).map(r => <span key={r.id} className="rounded-full bg-gray-100 px-3 py-1 text-xs">{r.name}: <b>{r.state}{r.attributes.unit_of_measurement ? ` ${r.attributes.unit_of_measurement}` : ""}</b></span>)}</div></div>)}
    {rows && rows.length > 0 && <p className="text-xs text-gray-500">Usage is billed by Imou above 30,000 requests per App ID each month. If quota runs out quickly, remove devices you do not need.</p>}
  </div>;
}

function CameraCard({ cam, homeId, request, call, ptz }: { cam: Entity; homeId: string; request: Requester; call: Call; ptz: Entity[] }) {
  const [url, setUrl] = useState(""); const [note, setNote] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (!url) return; const t = setTimeout(() => setUrl(""), 30000); return () => { clearTimeout(t); URL.revokeObjectURL(url); }; }, [url]);
  const view = async () => { setBusy(true); setNote(""); try { const res = await request(`/api/iot/homes/${homeId}/devices/${cam.id}/snapshot`, { cache: "no-store" }); if (!res.ok) throw new Error("Camera access needs your approval, or the camera is offline"); setUrl(URL.createObjectURL(await res.blob())); } catch (e) { setNote((e as Error).message); } finally { setBusy(false); } };
  const move = async (row: Entity) => { setNote(""); try { const r = await call<{ ok: boolean; message: string }>(`/${homeId}/devices/${row.id}/ptz`, { method: "POST", headers: json, body: JSON.stringify({ direction: row.ptz }) }); if (!r.ok) setNote(r.message); } catch (e) { setNote((e as Error).message); } };
  const pad = (dir: string) => ptz.find(p => p.ptz === dir);
  const icons: Record<string, React.ReactNode> = { up: <ArrowUp className="h-4 w-4" />, left: <ArrowLeft className="h-4 w-4" />, right: <ArrowRight className="h-4 w-4" />, down: <ArrowDown className="h-4 w-4" /> };
  return <article className="rounded-xl border p-3"><p className="flex items-center gap-2 font-medium"><Camera className="h-4 w-4 text-cyan-600" />{cam.name}<span className="ml-auto text-xs text-gray-500">{cam.state}</span></p>
    <button className={button + " mt-3"} disabled={busy} onClick={() => void view()}>View current snapshot</button>
    {url && <img className="mt-3 w-full rounded-lg" alt={`Snapshot from ${cam.name}`} src={url} />}
    {ptz.length > 0 && <div className="mt-3 grid w-32 grid-cols-3 gap-1" aria-label="Camera movement">{[["", "up", ""], ["left", "", "right"], ["", "down", ""]].flat().map((dir, i) => dir && pad(dir) ? <button key={i} aria-label={`Move camera ${dir}`} className={button + " flex justify-center px-2"} onClick={() => void move(pad(dir)!)}>{icons[dir]}</button> : <span key={i} />)}</div>}
    {note && <p role="alert" className="mt-2 text-sm text-red-700">{note}</p>}</article>;
}
