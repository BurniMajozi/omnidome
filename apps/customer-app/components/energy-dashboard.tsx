"use client";
import React, { useState } from "react";
import { Battery, Droplets, Flame, House, Sun, UtilityPole, ChevronLeft, ChevronRight, CalendarDays } from "lucide-react";

type Total = { value: number | null; unit: string; reason: string | null };
export type EnergyReport = { totals: Record<string, Total>; power: Record<string, { time: string; kw: number }[]>; grid_cost_zar: number | null; note: string; flows?: Record<string, boolean> };
const palette = { grid: "#488fcc", solar: "#ff9800", battery: "#36b9b5", home: "#253744", gas: "#ad1239", water: "#00b8d4" };
const panel = "min-w-0 rounded-2xl border border-gray-200 bg-white p-5 sm:p-6";
const names: Record<string, string> = { grid_power: "Grid", solar_power: "Solar", battery_power: "Battery", home_power: "Home" };
function text(total?: Total) {
  return total?.value == null ? "—" : total.value.toLocaleString("en-ZA", { maximumFractionDigits: 2 }) + " " + total.unit;
}
function homeTotal(totals: Record<string, Total>): Total {
  const keys = ["grid_import", "grid_export", "solar", "battery_charge", "battery_discharge"];
  if (keys.some(key => totals[key]?.value == null)) return { value: null, unit: "kWh", reason: "Connect import, export, solar and battery meters to calculate home consumption." };
  const value = totals.grid_import.value! + totals.solar.value! + totals.battery_discharge.value! - totals.grid_export.value! - totals.battery_charge.value!;
  return { value: value >= 0 ? value : null, unit: "kWh", reason: value >= 0 ? null : "Meter balance needs review." };
}
function Flow({ report }: { report: EnergyReport | null }) {
  const totals = report?.totals || {};
  const nodes = [
    { name: "Grid", x: 70, y: 250, color: palette.grid, icon: UtilityPole, lines: [["← " + text(totals.grid_export), "#8b5cf6"], ["→ " + text(totals.grid_import), palette.grid]] },
    { name: "Solar", x: 230, y: 100, color: palette.solar, icon: Sun, lines: [[text(totals.solar), palette.solar]] },
    { name: "Home", x: 430, y: 250, color: palette.grid, icon: House, lines: [[text(homeTotal(totals)), palette.home]] },
    { name: "Battery", x: 230, y: 400, color: palette.battery, icon: Battery, lines: [["↓ " + text(totals.battery_charge), "#e65b8c"], ["↑ " + text(totals.battery_discharge), palette.battery]] },
    { name: "Gas", x: 430, y: 100, color: palette.gas, icon: Flame, lines: [[text(totals.gas), palette.gas]] },
    { name: "Water", x: 430, y: 400, color: palette.water, icon: Droplets, lines: [[text(totals.water), palette.water]] },
  ];
  const paths = [
    ["grid_import", "M122 250H376", palette.grid],
    ["grid_export", "M376 234H122", "#8b5cf6"],
    ["solar", "M212 152C212 230 174 234 122 234", "#8b5cf6"],
    ["solar", "M248 152C248 225 275 234 376 234", palette.solar],
    ["solar", "M230 152V348", palette.solar],
    ["battery_discharge", "M248 348C248 275 288 266 376 266", palette.battery],
    ["battery_charge", "M376 282C288 282 212 279 212 348", palette.home],
    ["gas", "M430 152V196", palette.gas],
    ["water", "M430 348V304", palette.water],
  ];
  return <svg viewBox="0 0 510 480" className="mx-auto w-full max-w-xl" role="img" aria-label="Energy distribution between grid, solar, home, battery, gas and water">
    <style>{"@media (prefers-reduced-motion: reduce) { .energy-flow-dot { display: none; } }"}</style>
    {paths.map(([key, path, color], index) => <g key={index}><path d={path} stroke={color} strokeWidth={report?.flows?.[key] ? 2 : 1.6} fill="none" opacity={totals[key]?.value == null && !report?.flows?.[key] ? .25 : .85} />{report?.flows?.[key] && [0, 3, 5, 6, 7, 8].includes(index) && <circle className="energy-flow-dot" r="4" fill={color}><animateMotion dur="3s" repeatCount="indefinite" path={path} /></circle>}{report?.flows?.[key] && index === 1 && <circle className="energy-flow-dot" r="4" fill={color}><animateMotion dur="3s" repeatCount="indefinite" path={path} /></circle>}</g>)}
    {nodes.map(node => { const Icon = node.icon; return <g key={node.name}>
      <circle cx={node.x} cy={node.y} r="52" fill="white" stroke={node.color} strokeWidth={node.name === "Home" ? 5 : 2} />
      <Icon x={node.x - 14} y={node.y - 30} width={28} height={28} color="#202529" strokeWidth={2} />
      {node.lines.map(([line, color], i) => <text key={i} x={node.x} y={node.y + (node.lines.length > 1 ? 10 : 15) + i * 18} fill={color} textAnchor="middle" fontSize="16">{line}</text>)}
      <text x={node.x} y={node.y + 74} textAnchor="middle" fontSize="18" fill="#526273">{node.name}</text>
    </g>; })}
  </svg>;
}
function PowerSources({ report }: { report: EnergyReport | null }) {
  const series = Object.entries(report?.power || {}).map(([key, points]) => [key, points.filter(point => Number.isFinite(point.kw) && Number.isFinite(Date.parse(point.time)))] as const).filter(([, points]) => points.length);
  const points = series.flatMap(([, values]) => values);
  if (points.length < 2) return <div className="flex min-h-64 flex-col items-center justify-center rounded-xl bg-gray-50 px-6 text-center"><Sun className="mb-3 text-gray-400" size={32} /><p className="font-medium text-gray-700">Waiting for power readings</p><p className="mt-2 text-sm text-gray-500">Connect power sensors to see grid, solar, battery and home usage over time.</p></div>;
  const minT = Math.min(...points.map(p => Date.parse(p.time))), maxT = Math.max(...points.map(p => Date.parse(p.time)));
  const low = Math.min(0, ...points.map(p => p.kw)), high = Math.max(1, ...points.map(p => p.kw));
  const colors: Record<string, string> = { grid_power: palette.grid, solar_power: palette.solar, battery_power: palette.battery, home_power: palette.home };
  return <><svg viewBox="0 0 480 290" className="w-full" role="img" aria-label="Recorded power in kilowatts over time">
    <text x="38" y="18" fill="#64748b" fontSize="12">kW</text>
    {[0, 1, 2, 3, 4].map(i => <g key={i}><path d={`M42 ${30 + i * 50}H468`} stroke="#e5e7eb" /><text x="34" y={34 + i * 50} textAnchor="end" fontSize="11" fill="#64748b">{(high - (high - low) * i / 4).toFixed(1)}</text></g>)}
    {series.map(([key, values]) => <polyline key={key} fill="none" stroke={colors[key] || palette.home} strokeWidth="1.8" points={values.map(p => `${42 + (Date.parse(p.time) - minT) / (maxT - minT || 1) * 426},${230 - (p.kw - low) / (high - low) * 200}`).join(" ")} />)}
    {[0, 1, 2, 3].map(i => <text key={i} x={42 + i * 142} y="257" textAnchor={i === 0 ? "start" : i === 3 ? "end" : "middle"} fontSize="11" fill="#64748b">{new Date(minT + (maxT - minT) * i / 3).toLocaleTimeString("en-ZA", { timeZone: "Africa/Johannesburg", hour: "2-digit", minute: "2-digit" })}</text>)}
  </svg><div className="flex flex-wrap gap-4 text-xs">{series.map(([key]) => <span key={key} className="flex items-center gap-2"><span className="h-2 w-2 rounded-full" style={{ background: colors[key] }} />{names[key] || key}</span>)}</div></>;
}
export default function EnergyDashboard({ report, day, onDayChange }: { report: EnergyReport | null; day: string; onDayChange: (day: string) => void }) {
  const [section, setSection] = useState("Summary");
  const totals = report?.totals || {};
  const rows = [
    { label: "Solar total", total: totals.solar, color: palette.solar },
    { label: "Battery discharge", total: totals.battery_discharge, color: palette.battery },
    { label: "Battery charge", total: totals.battery_charge, color: "#e65b8c" },
    { label: "Grid import", total: totals.grid_import, color: palette.grid, cost: report?.grid_cost_zar },
    { label: "Grid export", total: totals.grid_export, color: "#8b5cf6" },
    { label: "Gas total", total: totals.gas, color: palette.gas },
    { label: "Water total", total: totals.water, color: palette.water },
  ];
  const moveDay = (offset: number) => { const date = new Date(day + "T12:00:00Z"); date.setUTCDate(date.getUTCDate() + offset); onDayChange(date.toISOString().slice(0, 10)); };
  return <div className="space-y-5 text-gray-900">
    <nav aria-label="Energy categories" className="flex gap-1 overflow-x-auto border-b border-gray-200">{["Summary", "Electricity", "Gas", "Water", "Now"].map(name => <button key={name} aria-current={section === name ? "page" : undefined} onClick={() => setSection(name)} className={"whitespace-nowrap border-b-2 px-5 py-3 text-sm font-medium " + (section === name ? "border-gray-900 text-gray-900" : "border-transparent text-gray-500 hover:text-gray-900")}>{name}</button>)}</nav>
    <div className="grid items-start gap-5 2xl:grid-cols-3 lg:grid-cols-2">
      {(section === "Summary" || section === "Electricity") && <section className={panel}><h4 className="text-2xl font-medium">Energy distribution</h4><Flow report={report} /><p className="text-xs leading-5 text-gray-500">Recorded totals for the selected day. Moving dots show fresh measured flow; offline or stale meters stay still. Faded connections have no readings. Home use is calculated only when all balance meters are available.</p></section>}
      {section !== "Now" && <section className={panel}><h4 className="mb-5 text-2xl font-medium">Totals</h4><table className="w-full text-sm"><thead><tr className="border-b text-left"><th className="pb-4 font-medium">Source</th><th className="pb-4 text-right font-medium">Usage</th><th className="pb-4 text-right font-medium">Cost</th></tr></thead><tbody>{rows.filter(row => section === "Summary" || section === "Electricity" && !["Gas total", "Water total"].includes(row.label) || section === "Gas" && row.label === "Gas total" || section === "Water" && row.label === "Water total").map(row => <tr key={row.label} className="border-b last:border-0"><td className="py-4 pr-3"><div className="flex items-center gap-3"><span className="h-5 w-8 shrink-0 rounded border" style={{ borderColor: row.color, background: row.color + "55" }} /><span>{row.label}</span></div>{row.total?.value == null && <p className="mt-1 text-xs text-gray-500">{row.total?.reason || "Waiting for readings"}</p>}</td><td className="whitespace-nowrap py-4 text-right tabular-nums">{text(row.total)}</td><td className="py-4 pl-3 text-right tabular-nums">{row.cost != null ? "R" + row.cost.toFixed(2) : "—"}</td></tr>)}</tbody></table></section>}
      {(section === "Summary" || section === "Electricity" || section === "Now") && <section className={panel}><h4 className="mb-5 text-2xl font-medium">{section === "Now" ? "Latest recorded power" : "Power sources"}</h4><PowerSources report={report} />{section === "Now" && <p className="mt-3 text-xs text-gray-500">Recorded sensor readings; refresh the report to retrieve the latest available data.</p>}</section>}
    </div>
    {(section === "Summary" || section === "Gas" || section === "Water") && <div className="grid gap-5 md:grid-cols-3">{[{ title: "Electricity", total: homeTotal(totals), icon: House, color: palette.grid }, { title: "Gas consumption", total: totals.gas, icon: Flame, color: palette.gas }, { title: "Water consumption", total: totals.water, icon: Droplets, color: palette.water }].filter(row => section === "Summary" || section === "Gas" && row.title === "Gas consumption" || section === "Water" && row.title === "Water consumption").map(row => { const Icon = row.icon; return <section className={panel} key={row.title}><div className="flex items-center justify-between gap-3"><h4 className="text-lg font-medium">{row.title}</h4><Icon size={22} color={row.color} /></div><p className="my-5 text-3xl font-light tabular-nums">{text(row.total)}</p><p className="text-xs leading-5 text-gray-500">{row.total?.reason || "Total for the recorded portion of this day."}</p></section>; })}</div>}
    <div className="mx-auto flex w-fit max-w-full flex-wrap items-center justify-center gap-3 rounded-2xl border bg-white px-4 py-3 shadow-sm"><CalendarDays size={21} className="text-gray-600" /><input aria-label="Energy report date" type="date" value={day} onChange={e => { if (e.target.value) onDayChange(e.target.value); }} className="min-w-0 bg-transparent text-sm font-medium" /><button onClick={() => onDayChange(new Intl.DateTimeFormat("en-CA", { timeZone: "Africa/Johannesburg" }).format(new Date()))} className="rounded-full bg-cyan-50 px-4 py-2 text-sm font-medium text-cyan-700">Today</button><button aria-label="Previous day" onClick={() => moveDay(-1)} className="rounded-lg p-2 hover:bg-gray-100"><ChevronLeft size={20} /></button><button aria-label="Next day" onClick={() => moveDay(1)} className="rounded-lg p-2 hover:bg-gray-100"><ChevronRight size={20} /></button></div>
    <p className="text-xs leading-5 text-gray-500">{report?.note || "Waiting for recorded meter readings. Choose meters to connect your energy sources."}</p>
  </div>;
}

