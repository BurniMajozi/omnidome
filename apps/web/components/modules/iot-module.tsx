"use client"

import React from "react"
import { ModuleLayout } from "./module-layout"
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer,
    PieChart,
    Pie,
    Cell,
    AreaChart,
    Area,
} from "recharts"
import { Radio, Signal, Thermometer, Zap, Cpu, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { NotConnected, NoDataYet } from "@/components/ui/not-connected"
import { tileLabel, type Loadable } from "@/lib/service-state"
import { loadIotAlerts, loadIotDevices, loadIotEvents, useOps } from "@/lib/ops-api"
import {
    allSettled,
    countBy,
    dataOr,
    deviceStats,
    eventsPerHour,
    fmtInt,
    pct,
    relativeTime,
    type IotDeviceRow,
    type IotEventRow,
} from "@/lib/ops-derive"

/**
 * IoT & Devices. Read from the IoT service (Home Assistant devices, alert rules
 * and the event log). The service tracks smart-home style devices, not fibre
 * ONT optical power, so there are no RX-power / dBm figures here. Sections
 * without a real source say so.
 */

const STATUS_COLORS: Record<string, string> = {
    online: "#4ade80",
    offline: "#ef4444",
    unavailable: "#eab308",
    error: "#f97316",
    updating: "#60a5fa",
}

const tooltipStyle = { backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }

const tableColumns = [
    { key: "name", label: "Device" },
    { key: "type", label: "Type" },
    { key: "domain", label: "Domain" },
    { key: "status", label: "Status" },
    { key: "battery", label: "Battery" },
    { key: "signal", label: "Signal" },
    { key: "lastSeen", label: "Last Seen" },
]

const iotKpiIconMap: Record<string, React.ReactNode> = {
    devices: <Radio className="h-5 w-5 text-emerald-400" />,
    online: <Signal className="h-5 w-5 text-blue-400" />,
    alerts: <Zap className="h-5 w-5 text-amber-400" />,
    battery: <Thermometer className="h-5 w-5 text-violet-400" />,
}

const tile = (l: Loadable<unknown>, value: () => string) => (l.state === "ready" ? value() : (tileLabel(l) ?? "—"))

export function IoTModule() {
    const devices = useOps(loadIotDevices)
    const alerts = useOps(loadIotAlerts)
    const events = useOps(loadIotEvents)

    const reloadAll = () => {
        devices.reload()
        alerts.reload()
        events.reload()
    }

    if (!allSettled(devices.value, alerts.value, events.value)) {
        return (
            <div className="space-y-4" aria-busy="true" aria-label="Loading IoT data">
                <div className="h-16 animate-pulse rounded-lg bg-muted/50" />
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {[0, 1, 2, 3].map((i) => (
                        <div key={i} className="h-28 animate-pulse rounded-lg bg-muted/50" />
                    ))}
                </div>
                <div className="h-64 animate-pulse rounded-lg bg-muted/50" />
            </div>
        )
    }

    const deviceRows: IotDeviceRow[] = devices.value.state === "ready" ? devices.value.data.rows : []
    const deviceTotal = devices.value.state === "ready" ? devices.value.data.total : 0
    const alertRows: any[] = alerts.value.state === "ready" ? alerts.value.data.rows : []
    const alertTotal = alerts.value.state === "ready" ? alerts.value.data.total : 0
    const eventRows: IotEventRow[] = dataOr(events.value, { items: [] as IotEventRow[], total: 0 }).items
    const eventTotal = dataOr(events.value, { items: [] as IotEventRow[], total: 0 }).total

    const stats = deviceStats(deviceRows)
    const statusPie = Object.entries(stats.byStatus).map(([name, value]) => ({ name, value, fill: STATUS_COLORS[name] ?? "#737373" }))
    const hourly = eventsPerHour(eventRows)
    const eventTypes = Object.entries(countBy(eventRows, (e) => e.event_type))
        .map(([type, count]) => ({ type, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    const enabledAlerts = alertRows.filter((a) => a.is_enabled).length
    const offline = deviceRows.filter((d) => d.status !== "online")
    const sample = deviceRows.length < deviceTotal ? ` Based on the first ${fmtInt(deviceRows.length)} of ${fmtInt(deviceTotal)} devices.` : ""

    const flashcardKPIs = [
        {
            id: "1",
            title: "Total Devices",
            value: tile(devices.value, () => fmtInt(deviceTotal)),
            change: "",
            changeType: "neutral" as const,
            iconKey: "devices",
            backTitle: "Device Breakdown",
            backDetails: stats.byType.slice(0, 5).map((t) => ({ label: t.type, value: fmtInt(t.count) })),
            backInsight: `${fmtInt(stats.online)} of ${fmtInt(stats.total)} loaded devices are online.${sample}`,
        },
        {
            id: "2",
            title: "Online Rate",
            value: tile(devices.value, () => (stats.total ? pct(stats.online, stats.total) : "No data yet")),
            change: "",
            changeType: "neutral" as const,
            iconKey: "online",
            backTitle: "Status",
            backDetails: Object.entries(stats.byStatus).map(([label, value]) => ({ label, value: fmtInt(value) })),
            backInsight: `Share of devices reporting online.${sample}`,
        },
        {
            id: "3",
            title: "Alert Rules",
            value: tile(alerts.value, () => fmtInt(alertTotal)),
            change: "",
            changeType: "neutral" as const,
            iconKey: "alerts",
            backTitle: "Alert Rules",
            backDetails: [
                { label: "Enabled", value: fmtInt(enabledAlerts) },
                { label: "Disabled", value: fmtInt(alertRows.length - enabledAlerts) },
                { label: "Times triggered", value: fmtInt(alertRows.reduce((n, a) => n + (Number(a.trigger_count) || 0), 0)) },
            ],
            backInsight: "Configured alert rules; not a count of currently firing alerts.",
        },
        {
            id: "4",
            title: "Low Battery",
            value: tile(devices.value, () => (stats.withBattery ? fmtInt(stats.lowBattery) : "No data yet")),
            change: "",
            changeType: "neutral" as const,
            iconKey: "battery",
            backTitle: "Battery",
            backDetails: [
                { label: "Below 20%", value: fmtInt(stats.lowBattery) },
                { label: "Devices reporting battery", value: fmtInt(stats.withBattery) },
            ],
            backInsight: "Devices reporting a battery level under 20%.",
        },
    ].map((kpi) => ({ ...kpi, icon: iotKpiIconMap[kpi.iconKey] || <Radio className="h-5 w-5 text-primary" /> }))

    const summary =
        devices.value.state === "ready"
            ? `${fmtInt(deviceTotal)} IoT devices registered, ${fmtInt(stats.online)} online.${sample} ` +
              `${fmtInt(alertTotal)} alert rules configured (${fmtInt(enabledAlerts)} enabled). ` +
              (events.value.state === "ready" ? `${fmtInt(eventTotal)} events on record.` : "The event log could not be read.")
            : "Device figures are unavailable because the IoT service could not be read. Nothing is estimated in its place."

    return (
        <ModuleLayout
            title="IoT & Device Management"
            icon={<Cpu className="h-5 w-5" />}
            subtitle="Device fleet, sensor telemetry, and IoT connectivity status"
            headerActions={
                <Button variant="outline" size="sm" onClick={reloadAll}>
                    <RefreshCw className="h-3.5 w-3.5" />
                    Refresh
                </Button>
            }
            flashcardKPIs={flashcardKPIs}
            activities={eventRows.slice(0, 15).map((e) => ({
                id: e.id,
                user: e.source || "System",
                action: `${e.event_type.replace(/_/g, " ")}${e.message ? ":" : ""}`,
                target: e.message ?? "",
                time: relativeTime(e.created_at),
                type: "update" as const,
            }))}
            issues={offline.slice(0, 20).map((d) => ({
                id: d.id,
                title: `${d.friendly_name} is ${d.status}`,
                severity: (d.status === "error" ? "high" : d.status === "offline" ? "medium" : "low") as "high" | "medium" | "low",
                status: "open" as const,
                assignee: "Unassigned",
                time: relativeTime(d.last_seen),
            }))}
            summary={summary}
            tasks={[]}
            aiRecommendations={[]}
            tableData={deviceRows.slice(0, 200).map((d) => ({
                id: d.id,
                name: d.friendly_name,
                type: d.device_type,
                domain: d.ha_domain ?? "—",
                status: d.status,
                battery: typeof d.battery_level === "number" ? `${d.battery_level}%` : "—",
                signal: typeof d.signal_strength === "number" ? d.signal_strength : "—",
                lastSeen: relativeTime(d.last_seen),
            }))}
            tableColumns={tableColumns}
        >
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Device status */}
                <div className="surface-card p-6">
                    <h4 className="card-title mb-4">Device Status</h4>
                    {devices.value.state !== "ready" ? (
                        <NotConnected loadable={devices.value} service="IoT" onRetry={devices.reload} />
                    ) : statusPie.length === 0 ? (
                        <NoDataYet message="No devices registered yet" />
                    ) : (
                        <ResponsiveContainer width="100%" height={300}>
                            <PieChart>
                                <Pie data={statusPie} cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={3} dataKey="value" label={({ value }) => `${value}`}>
                                    {statusPie.map((entry) => (
                                        <Cell key={entry.name} fill={entry.fill} />
                                    ))}
                                </Pie>
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    )}
                </div>

                {/* Device types online/offline */}
                <div className="surface-card p-6">
                    <h4 className="card-title mb-4">Device Status by Type</h4>
                    {devices.value.state !== "ready" ? (
                        <NotConnected loadable={devices.value} service="IoT" onRetry={devices.reload} />
                    ) : stats.byType.length === 0 ? (
                        <NoDataYet message="No devices registered yet" />
                    ) : (
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={stats.byType}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                <XAxis dataKey="type" stroke="#888" fontSize={11} />
                                <YAxis allowDecimals={false} stroke="#888" fontSize={12} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Legend />
                                <Bar dataKey="online" fill="#4ade80" name="Online" stackId="a" />
                                <Bar dataKey="offline" fill="#ef4444" name="Not online" stackId="a" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>

                {/* Event activity */}
                <div className="surface-card p-6">
                    <h4 className="card-title mb-4">Event Activity (24h)</h4>
                    {events.value.state !== "ready" ? (
                        <NotConnected loadable={events.value} service="IoT events" onRetry={events.reload} />
                    ) : eventRows.length === 0 ? (
                        <NoDataYet message="No events recorded yet" />
                    ) : (
                        <ResponsiveContainer width="100%" height={300}>
                            <AreaChart data={hourly}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                <XAxis dataKey="hour" stroke="#888" fontSize={12} interval={3} />
                                <YAxis allowDecimals={false} stroke="#888" fontSize={12} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Area type="monotone" dataKey="events" stroke="#60a5fa" fill="#60a5fa33" name="Events" />
                            </AreaChart>
                        </ResponsiveContainer>
                    )}
                </div>

                {/* Events by type */}
                <div className="surface-card p-6">
                    <h4 className="card-title mb-4">Events by Type</h4>
                    {events.value.state !== "ready" ? (
                        <NotConnected loadable={events.value} service="IoT events" onRetry={events.reload} />
                    ) : eventTypes.length === 0 ? (
                        <NoDataYet message="No events recorded yet" />
                    ) : (
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={eventTypes}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                                <XAxis dataKey="type" stroke="#888" fontSize={11} />
                                <YAxis allowDecimals={false} stroke="#888" fontSize={12} />
                                <Tooltip contentStyle={tooltipStyle} />
                                <Bar dataKey="count" fill="#a855f7" name="Events" radius={[4, 4, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    )}
                </div>
            </div>
        </ModuleLayout>
    )
}
