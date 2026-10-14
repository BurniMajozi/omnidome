"use client";
import { useEffect, useRef, useState } from "react";
import { BarChart3, Download, RefreshCw, ArrowUpRight, Sparkles, X, Check, Clock3 } from "lucide-react";
import styles from "./home-reports.module.css";

type Point = { date: string; value: number; samples: number };
type Series = { entity_id: string; name: string; room: string | null; unit: string; kind: string; source: string; points: Point[]; skipped_samples: number; total: number | null; average: number | null };
type Report = { plan: string; series: Series[]; last_sync_at: string | null; gateway_status: string; upgrade_status: string | null; note: string };
type Call = <T>(path: string, init?: RequestInit) => Promise<T>;
const stamp = (date: string) => new Date(date + "T12:00:00").toLocaleDateString("en-ZA", { day: "numeric", month: "short" });
const examples: Series[] = [
  { entity_id: "sample.energy", name: "Grid consumption", room: "Whole home", unit: "kWh", kind: "consumption", source: "sample", total: null, average: null, skipped_samples: 0, points: [] },
  { entity_id: "sample.water", name: "Water consumption", room: "Whole home", unit: "L", kind: "consumption", source: "sample", total: null, average: null, skipped_samples: 0, points: [] },
  { entity_id: "sample.temperature", name: "Living room temperature", room: "Living room", unit: "°C", kind: "measurement", source: "sample", total: null, average: null, skipped_samples: 0, points: [] },
].map((row, metric) => {
  const points = Array.from({ length: 30 }, (_, day) => ({ date: new Date(Date.UTC(2026, 8, day + 1)).toISOString().slice(0, 10),
    value: Math.round((metric === 0 ? 8 + Math.sin(day * .7) * 2 + (day % 7 > 4 ? 3 : 0) : metric === 1 ? 210 + Math.cos(day) * 45 : 22 + Math.sin(day * .3) * 2) * 10) / 10, samples: 24 }));
  return { ...row, points };
});

export default function HomeReports({ homeId, owner, call }: { homeId: string; owner: boolean; call: Call }) {
  const [report, setReport] = useState<Report | null>(null), [error, setError] = useState(""), [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true), [sample, setSample] = useState(false), [days, setDays] = useState(30), [selected, setSelected] = useState("");
  const [success, setSuccess] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const load = async () => {
    setError(""); setLoading(true);
    try { const data = await call<Report>(`/${homeId}/reports`); setReport(data); setSample(!data.series.length); }
    catch (e) { setError((e as Error).message); }
    finally { setLoading(false); }
  };
  useEffect(() => { let alive = true; setLoading(true);
    void call<Report>(`/${homeId}/reports`).then(data => { if (alive) { setReport(data); setSample(!data.series.length); } })
      .catch(e => { if (alive) setError(e.message); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [homeId, call]);
  const rows = sample ? examples : report?.series || [], current = rows.find(row => row.entity_id === selected) || rows[0];
  const points = current?.points.filter(row => row.date >= new Date(Date.parse((current.points.at(-1)?.date || "2026-09-30") + "T12:00:00Z") - (days - 1) * 86400000).toISOString().slice(0, 10)) || [];
  const total = points.length ? points.reduce((sum, row) => sum + row.value, 0) : null;
  const summary = total === null ? "—" : (current?.kind === "consumption" ? total : total / points.length).toLocaleString("en-ZA", { maximumFractionDigits: 1 });
  const saveRequest = async () => {
    setBusy(true); setError("");
    try { const response = await call<{ status: string; message: string }>(`/${homeId}/reporting/upgrade`, { method: "POST" });
      setReport(previous => previous ? { ...previous, upgrade_status: response.status } : previous); setSuccess(response.message); dialog.current?.close(); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };
  const importHistory = async () => {
    setBusy(true); setSuccess(""); setError("");
    try { const result = await call<{ samples: number }>(`/${homeId}/reports/import`, { method: "POST" }); await load(); setSuccess(`Imported ${result.samples} hourly observations. Missing history stays blank.`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const exportCsv = () => {
    const safe = (value: string | number) => '"' + String(value).replace(/^[=+@-]/, "'$&").replaceAll('"', '""') + '"';
    const csv = [["source", "sensor", "date", "value", "unit", "samples"], ...points.map(p => [sample ? "SAMPLE — not household data" : current.source, current.name, p.date, p.value, current.unit, p.samples])].map(row => row.map(safe).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })), link = document.createElement("a");
    link.href = url; link.download = `homedome-${sample ? "sample" : "report"}.csv`; link.click(); URL.revokeObjectURL(url);
  };
  return <div className={styles.workspace}>
    <header className={styles.header}><div><span className={styles.eyebrow}>YOUR HOME, OVER TIME</span><h3>Home reports</h3><p>Understand your consumption, comfort and changing patterns.</p></div>
      <div className={styles.actions}><button className={styles.button} onClick={() => void load()} disabled={busy}><RefreshCw size={15} />Refresh</button>
        {owner && <button className={styles.primary} onClick={() => dialog.current?.showModal()}><Sparkles size={16} />{report?.upgrade_status && report.upgrade_status !== "closed" ? "View upgrade request" : "Upgrade reporting"}<ArrowUpRight size={16} /></button>}</div></header>
    {error && <div role="alert" className={styles.error}>{error}<button className={styles.button} onClick={() => void load()}>Try again</button></div>}
    {success && <p role="status" className={styles.banner}>{success}</p>}
    {loading ? <div className={styles.skeleton} role="status" aria-label="Loading home reports">Loading reports…</div> : !report ? null : <>
      <div className={styles.mode}><div><span className={styles.badge}>{sample ? "Sample reports" : "Included reporting"}</span><span>{sample ? "Illustrative September data. Nothing here is a reading from your home." : "Your readings • up to 30 days • Africa/Johannesburg"}</span></div>
        <button className={styles.button} onClick={() => { setSample(!sample); setSelected(""); }}>{sample ? "View my data" : "Explore sample reports"}</button></div>
      {!sample && !rows.length ? <div className={styles.empty}><BarChart3 size={36} /><h4>Your first report starts with a sensor</h4><p>No reportable readings yet. Explore the sample charts now; connect and sync sensors when your products arrive.</p><button className={styles.primary} onClick={() => setSample(true)}>Explore sample reports</button></div> : <>
        <div className={styles.toolbar}><label>Report<select value={current?.entity_id || ""} onChange={e => setSelected(e.target.value)}>{rows.map(row => <option key={row.entity_id} value={row.entity_id}>{row.name}{row.room ? " · " + row.room : ""}</option>)}</select></label>
          <div className={styles.range} aria-label="Report period">{[7, 14, 30].map(n => <button key={n} aria-pressed={days === n} onClick={() => setDays(n)}>{n} days</button>)}</div>
          <button className={styles.button} disabled={!points.length} onClick={exportCsv}><Download size={15} />Export {sample ? "sample" : "CSV"}</button></div>
        <div className={styles.grid}><article className={styles.chartCard}><div className={styles.chartHeading}><div><span className={styles.eyebrow}>{current?.kind === "consumption" ? "RECORDED CONSUMPTION" : "DAILY MEASUREMENTS"}</span><h4>{current?.name}</h4></div><span>{current?.unit}</span></div>
          <ReportChart points={points} unit={current?.unit || ""} sample={sample} />
          <details className={styles.data}><summary>View daily values</summary><table><caption>{sample ? "Sample values" : "Available daily values"}</caption><thead><tr><th scope="col">Date</th><th scope="col">Value ({current?.unit})</th><th scope="col">Samples</th></tr></thead><tbody>{points.map(p => <tr key={p.date}><th scope="row">{stamp(p.date)}</th><td>{p.value}</td><td>{p.samples}</td></tr>)}</tbody></table></details>
          <p className={styles.caption}>{sample ? "Sample chart • September 2026" : "Available daily values only. Gaps are not zero; partial days may be incomplete."}</p></article>
          <aside className={styles.side}><article className={styles.stat}><span>{current?.kind === "consumption" ? "Recorded total" : "Mean of available daily values"}</span><strong>{summary} <small>{current?.unit}</small></strong><p>{points.length} days with data in this {days}-day view</p></article>
            <article className={styles.stat}><span>Data quality</span><strong>{sample ? "Illustrative" : report.gateway_status === "connected" ? "Connected" : "Historical"}</strong><p>{sample ? "These charts demonstrate the experience. They are not measurements." : `Source: ${current?.source === "recorder" ? "Home Assistant hourly statistics" : "HomeDome observations"}`}</p>
              {!sample && <p>{current?.skipped_samples || 0} unusable samples omitted. Last sync: {report.last_sync_at ? new Date(report.last_sync_at).toLocaleString("en-ZA") : "Not yet synced"}.</p>}</article></aside></div>
      </>}
      {!sample && <p className={styles.caption}>{report.note}</p>}
      {owner && <div className={styles.import}><div><h4>Bring in existing history</h4><p>Import up to 30 days for supported sensors already paired and synced. You can do this when your devices arrive.</p></div><button className={styles.button} disabled={busy} onClick={() => void importHistory()}>Import sensor history</button></div>}
      <div className={styles.upgrade}><div><span className={styles.eyebrow}>MORE FROM YOUR HOME</span><h4>A longer view. Less guesswork.</h4><p>Advanced reporting is being prepared: longer history, period comparisons, forecasts and scheduled summaries.</p><div className={styles.featureList}>{["Longer history", "Usage forecasts", "Scheduled summaries"].map(text => <span key={text}><Check size={14} />{text}</span>)}</div></div>
        {owner ? <button className={styles.primary} onClick={() => dialog.current?.showModal()}>Explore advanced reporting<ArrowUpRight size={16} /></button> : <span className={styles.badge}>Customer chooses their plan</span>}</div>
    </>}
    {owner && <dialog ref={dialog} className={styles.dialog} aria-labelledby="reporting-upgrade-title"><div className={styles.header}><div><span className={styles.eyebrow}>REPORTING OPTIONS</span><h3 id="reporting-upgrade-title">More insight, when you're ready</h3></div><button className={styles.button} aria-label="Close upgrade options" onClick={() => dialog.current?.close()}><X size={18} /></button></div>
      <p>Your existing home controls and basic reporting stay included.</p>
      <div className={styles.plans}><article><span className={styles.badge}>Your plan</span><h4>Included</h4><ul><li>Available history up to 30 days</li><li>Energy and room sensor charts</li><li>Manual CSV export</li></ul></article><article><span className={styles.badge}>Coming next</span><h4>Advanced reporting</h4><ul><li>Up to 12 months of selected statistics</li><li>Comparisons and validated forecasts</li><li>Scheduled summaries and alerts</li></ul></article></div>
      <p className={styles.banner}>Pricing is not published yet. Request the upgrade and your ISP will contact you with availability and a quote. This does not activate a paid plan or charge you.</p>
      {report?.upgrade_status && report.upgrade_status !== "closed" ? <p role="status" className={styles.badge}><Clock3 size={15} />{report.upgrade_status === "contacted" ? "Your ISP has marked this request as contacted" : "Upgrade requested — awaiting your ISP"}</p> : <button className={styles.primary} disabled={busy} onClick={() => void saveRequest()}>{busy ? "Saving request…" : "Request reporting upgrade"}<ArrowUpRight size={16} /></button>}
      {error && <p role="alert" className={styles.error}>{error}</p>}
    </dialog>}
  </div>;
}

export function ReportChart({ points, unit, sample }: { points: Point[]; unit: string; sample: boolean }) {
  const max = Math.max(1, ...points.map(p => p.value)), min = Math.min(0, ...points.map(p => p.value)), span = max - min;
  const width = 720, height = 220, start = Date.parse(points[0]?.date || "2026-09-01"), end = Date.parse(points.at(-1)?.date || "2026-09-30");
  const step = 640 / Math.max(1, Math.round((end - start) / 86400000) + 1), y = (value: number) => 185 - (value - min) / span * 155;
  return <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${sample ? "Sample " : ""}daily values in ${unit}. Values are listed in the table below.`}>
    {[0, .25, .5, .75, 1].map(n => <g key={n}><line x1="55" x2="702" y1={185 - n * 155} y2={185 - n * 155} stroke="var(--dome-line)" /><text x="45" y={189 - n * 155} textAnchor="end" fill="var(--dome-muted)" fontSize="11">{(min + span * n).toFixed(1)}</text></g>)}
    {points.map(p => <rect key={p.date} x={58 + Math.round((Date.parse(p.date) - start) / 86400000) * step} y={Math.min(y(0), y(p.value))} width={Math.max(2, step - 4)} height={Math.max(1, Math.abs(y(p.value) - y(0)))} rx="3" fill="#0891b2"><title>{`${stamp(p.date)}: ${p.value} ${unit}`}</title></rect>)}
    {points.length > 0 && <><text x="55" y="210" fill="var(--dome-muted)" fontSize="12">{stamp(points[0].date)}</text><text x="700" y="210" textAnchor="end" fill="var(--dome-muted)" fontSize="12">{stamp(points.at(-1)!.date)}</text></>}
  </svg>;
}

export function ReportingRequests({ call }: { call: Call }) {
  type Row = { id: string; home: string; customer_id: string; status: string; created_at: string };
  const [rows, setRows] = useState<Row[]>([]), [error, setError] = useState(""), [loading, setLoading] = useState(true), [busy, setBusy] = useState("");
  const load = async () => { try { setRows(await call<Row[]>("/reporting/requests")); setError(""); } catch (e) { setError((e as Error).message); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, [call]);
  const update = async (id: string, status: string) => { setBusy(id); try { await call("/reporting/requests/" + id, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(""); } };
  return <section className={styles.queue}><header className={styles.header}><div><h3>Reporting upgrades</h3><p>Customer requests for your tenant. Request status does not activate billing or grant access to private reports.</p></div><button className={styles.button} onClick={() => void load()}><RefreshCw size={15} />Refresh</button></header>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {loading ? <p role="status">Loading requests…</p> : !rows.length ? <p className={styles.empty}>No upgrade requests yet. Customers can request advanced reporting from HomeDome → Reports.</p> : rows.map(row => <article key={row.id} className={styles.request}><div><h4>{row.home}</h4><p>Requested {new Date(row.created_at).toLocaleDateString("en-ZA")} · Customer {row.customer_id.slice(0, 8)}</p></div><span className={styles.badge}>{row.status}</span><div className={styles.actions}>{row.status === "requested" && <button disabled={busy === row.id} className={styles.button} onClick={() => void update(row.id, "contacted")}>Mark contacted</button>}{row.status !== "closed" && <button disabled={busy === row.id} className={styles.button} onClick={() => void update(row.id, "closed")}>Close request</button>}</div></article>)}</section>;
}

