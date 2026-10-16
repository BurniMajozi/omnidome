"use client";
import React, { useCallback, useEffect, useState } from "react";
import { Home, Loader2, PlugZap, ShieldCheck } from "lucide-react";

type Call = <T>(path: string, init?: RequestInit) => Promise<T>;
type State = { managed: boolean; state: "own" | "active" | "fresh" | "needs_credentials" | "unavailable" };
const button = "rounded-lg border border-gray-300 px-3 py-2 text-sm font-medium hover:bg-gray-100 disabled:opacity-50";
const primary = "rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-50";
const input = "w-full rounded-lg border border-gray-300 bg-white p-2 text-gray-900";
const card = "rounded-2xl border border-gray-200 bg-white p-5";

// The prepared home gateway is activated here, in HomeDome. Customers never open Home Assistant.
export default function GatewayActivation({ homeId, call, onChanged, onDisconnect }: { homeId: string; call: Call; onChanged: () => void | Promise<void>; onDisconnect: () => void }) {
  const [status, setStatus] = useState<State | null>(null);
  const [login, setLogin] = useState({ username: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(() => { setError(""); call<State>(`/${homeId}/gateway`).then(setStatus).catch(e => setError(e.message)); }, [call, homeId]);
  useEffect(load, [load]);
  const activate = async (body: object) => {
    setBusy(true); setError("");
    try {
      await call(`/${homeId}/gateway/activate`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setLogin({ username: "", password: "" });
      await onChanged(); load();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  return <div className={card + " max-w-xl space-y-4"}>
    <div className="flex items-center gap-2"><Home className="h-5 w-5 text-cyan-600" /><h3 className="font-semibold">Your home gateway</h3></div>
    {error && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    {!status && !error && <p role="status" className="text-sm text-gray-600">Checking your gateway…</p>}
    {status?.state === "active" && <><p className="flex items-center gap-2 text-sm text-emerald-700"><ShieldCheck className="h-4 w-4" />Connected. Devices, rooms and integrations are managed from HomeDome.</p>
      <button className={button} onClick={onDisconnect}>Disconnect gateway</button></>}
    {status?.state === "fresh" && <><p className="text-sm text-gray-600">Your gateway is installed and waiting. Activating it sets your timezone, currency and units for South Africa and links it to this home. You will not need to sign in anywhere else.</p>
      <button className={primary} disabled={busy} onClick={() => void activate({})}>{busy ? <><Loader2 className="mr-1 inline h-4 w-4 animate-spin" />Activating…</> : <><PlugZap className="mr-1 inline h-4 w-4" />Activate your home</>}</button></>}
    {status?.state === "needs_credentials" && <form className="space-y-3" onSubmit={e => { e.preventDefault(); void activate(login); }}>
      <p className="text-sm text-gray-600">This gateway was set up before HomeDome took over. Enter its administrator login once to link it. HomeDome uses it for this single request, keeps only an encrypted access key, and never stores the password.</p>
      <label className="block text-sm">Administrator username<input required className={input} autoComplete="off" value={login.username} onChange={e => setLogin({ ...login, username: e.target.value })} /></label>
      <label className="block text-sm">Administrator password<input required type="password" className={input} autoComplete="new-password" value={login.password} onChange={e => setLogin({ ...login, password: e.target.value })} /></label>
      <button className={primary} disabled={busy}>{busy ? "Linking…" : "Link my home"}</button></form>}
    {status?.state === "unavailable" && <><p className="text-sm text-amber-900">The gateway is not reachable yet. It can take a minute after a restart.</p><button className={button} onClick={load}>Check again</button></>}
  </div>;
}
