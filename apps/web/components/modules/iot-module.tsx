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
    LineChart,
    Line,
    ScatterChart,
    Scatter,
    ZAxis,
} from "recharts"
import { Radio, Signal, Thermometer, Zap } from "lucide-react"
import { useModuleData } from "@/lib/module-data"

// Signal health distribution
const defaultSignalHealthData = [
    { name: "Excellent (> -15dBm)", value: 5420, fill: "#4ade80" },
    { name: "Good (-15 to -20dBm)", value: 2180, fill: "#60a5fa" },
    { name: "Fair (-20 to -25dBm)", value: 890, fill: "#eab308" },
    { name: "Degraded (-25 to -28dBm)", value: 156, fill: "#f97316" },
    { name: "Critical (< -28dBm)", value: 24, fill: "#ef4444" },
]

// Signal trend over time
const defaultSignalTrendData = [
    { hour: "00:00", avgRx: -17.2, alerts: 0, devices: 8670 },
    { hour: "04:00", avgRx: -17.1, alerts: 1, devices: 8668 },
    { hour: "08:00", avgRx: -17.4, alerts: 2, devices: 8672 },
    { hour: "12:00", avgRx: -17.8, alerts: 5, devices: 8670 },
    { hour: "16:00", avgRx: -18.1, alerts: 8, devices: 8665 },
    { hour: "20:00", avgRx: -17.6, alerts: 3, devices: 8670 },
]

// Device type breakdown
const defaultDeviceTypeData = [
    { type: "ONT", count: 6245, online: 6180, offline: 65 },
    { type: "Router", count: 1840, online: 1795, offline: 45 },
    { type: "Smart Camera", count: 342, online: 328, offline: 14 },
    { type: "Smart Bulb", count: 128, online: 119, offline: 9 },
    { type: "UPS Monitor", count: 115, online: 112, offline: 3 },
]

// At-risk devices scatter data (RX power vs temperature)
const defaultAtRiskDevicesData = [
    { device: "ONT-2847", rx: -27.2, temp: 52, region: "Cape Town" },
    { device: "ONT-3912", rx: -26.8, temp: 48, region: "JHB South" },
    { device: "ONT-1156", rx: -28.5, temp: 55, region: "Cape Town" },
    { device: "ONT-5423", rx: -25.9, temp: 44, region: "Durban" },
    { device: "ONT-7801", rx: -27.8, temp: 50, region: "Pretoria" },
    { device: "ONT-4290", rx: -26.2, temp: 46, region: "JHB North" },
    { device: "ONT-6134", rx: -29.1, temp: 58, region: "Cape Town" },
    { device: "ONT-8876", rx: -25.5, temp: 42, region: "Polokwane" },
]

// Command history
const defaultCommandHistoryData = [
    { month: "Jul", reboots: 45, toggles: 12, diagnostics: 89 },
    { month: "Aug", reboots: 38, toggles: 8, diagnostics: 92 },
    { month: "Sep", reboots: 52, toggles: 15, diagnostics: 78 },
    { month: "Oct", reboots: 41, toggles: 10, diagnostics: 95 },
    { month: "Nov", reboots: 35, toggles: 7, diagnostics: 102 },
    { month: "Dec", reboots: 28, toggles: 5, diagnostics: 110 },
]

const defaultFlashcardKPIs = [
    {
        id: "1",
        title: "Total Devices",
        value: "8,670",
        change: "+3.8%",
        changeType: "positive" as const,
        iconKey: "devices",
        backTitle: "Device Breakdown",
        backDetails: [
            { label: "ONTs", value: "6,245" },
            { label: "Routers", value: "1,840" },
            { label: "Smart Devices", value: "585" },
        ],
        backInsight: "98.4% of all devices currently online",
    },
    {
        id: "2",
        title: "Signal Alerts",
        value: "24",
        change: "-8",
        changeType: "positive" as const,
        iconKey: "alerts",
        backTitle: "Alert Distribution",
        backDetails: [
            { label: "Critical (< -28dBm)", value: "7" },
            { label: "Warning (-25 to -28)", value: "17" },
            { label: "Auto-Ticketed", value: "5" },
        ],
        backInsight: "Proactive tickets dispatched for 5 devices",
    },
    {
        id: "3",
        title: "Avg RX Power",
        value: "-17.4 dBm",
        change: "Stable",
        changeType: "neutral" as const,
        iconKey: "signal",
        backTitle: "Signal Quality",
        backDetails: [
            { label: "Excellent", value: "62.5%" },
            { label: "Good", value: "25.1%" },
            { label: "Below Threshold", value: "2.1%" },
        ],
        backInsight: "Network signal within healthy range",
    },
    {
        id: "4",
        title: "Remote Commands",
        value: "143",
        change: "+12%",
        changeType: "positive" as const,
        iconKey: "commands",
        backTitle: "Command Types (This Month)",
        backDetails: [
            { label: "Diagnostics", value: "110" },
            { label: "Remote Reboots", value: "28" },
            { label: "Power Toggles", value: "5" },
        ],
        backInsight: "Remote diagnostics reducing truck rolls by 22%",
    },
]

const iotKpiIconMap: Record<string, React.ReactNode> = {
    devices: <Radio className="h-5 w-5 text-emerald-400" />,
    alerts: <Zap className="h-5 w-5 text-amber-400" />,
    signal: <Signal className="h-5 w-5 text-blue-400" />,
    commands: <Thermometer className="h-5 w-5 text-violet-400" />,
}

const defaultActivities = [
    {
        id: "1",
        user: "Proactive Engine",
        action: "auto-created maintenance ticket for",
        target: "ONT-6134 (-29.1 dBm)",
        time: "3 minutes ago",
        type: "create" as const,
    },
    {
        id: "2",
        user: "NOC Team",
        action: "remotely rebooted",
        target: "ONT-2847 in Cape Town",
        time: "25 minutes ago",
        type: "update" as const,
    },
    {
        id: "3",
        user: "System",
        action: "ingested telemetry from",
        target: "8,670 devices",
        time: "1 hour ago",
        type: "update" as const,
    },
    {
        id: "4",
        user: "Lindiwe Zulu",
        action: "ran remote diagnostics on",
        target: "Region: JHB South",
        time: "2 hours ago",
        type: "assign" as const,
    },
    {
        id: "5",
        user: "Alert Engine",
        action: "escalated critical signal for",
        target: "ONT-1156 to NOC",
        time: "3 hours ago",
        type: "assign" as const,
    },
]

const defaultIssues = [
    {
        id: "1",
        title: "7 ONTs with critical signal below -28dBm in Cape Town",
        severity: "critical" as const,
        status: "in-progress" as const,
        assignee: "Field Team CT",
        time: "Active",
    },
    {
        id: "2",
        title: "ONT-6134 temperature at 58°C — exceeding safe range",
        severity: "high" as const,
        status: "open" as const,
        assignee: "NOC Team",
        time: "15 minutes ago",
    },
    {
        id: "3",
        title: "65 ONT devices offline across all regions",
        severity: "medium" as const,
        status: "in-progress" as const,
        assignee: "Network Ops",
        time: "1 hour ago",
    },
    {
        id: "4",
        title: "Firmware update pending for 340 routers",
        severity: "low" as const,
        status: "open" as const,
        assignee: "Engineering",
        time: "Scheduled",
    },
]

const defaultTasks = [
    {
        id: "1",
        title: "Dispatch technician to Cape Town for critical ONTs",
        priority: "urgent" as const,
        status: "in-progress" as const,
        dueDate: "Today",
        assignee: "Field Team CT",
    },
    {
        id: "2",
        title: "Roll out firmware update to 340 routers",
        priority: "high" as const,
        status: "todo" as const,
        dueDate: "This Week",
        assignee: "Engineering",
    },
    {
        id: "3",
        title: "Configure proactive alerts for Polokwane region",
        priority: "normal" as const,
        status: "todo" as const,
        dueDate: "Next Week",
        assignee: "NOC Team",
    },
    {
        id: "4",
        title: "Complete integration of new Smart Camera telemetry",
        priority: "normal" as const,
        status: "done" as const,
        dueDate: "Completed",
        assignee: "Engineering",
    },
]

const defaultAIRecommendations = [
    {
        id: "1",
        title: "Proactive fiber maintenance in Cape Town Site B",
        description: "15 ONTs showing signal degradation pattern. Dispatching before customer impact prevents ~R 45K in churn.",
        impact: "high" as const,
        category: "Proactive Health",
    },
    {
        id: "2",
        title: "Schedule overnight firmware rollout",
        description: "340 routers running vulnerable firmware. Off-peak window (02:00-04:00) minimizes customer impact.",
        impact: "high" as const,
        category: "Security",
    },
    {
        id: "3",
        title: "Add temperature monitoring to all ONTs",
        description: "3 devices overheating detected. Correlating temperature with signal degradation could predict failures 48h earlier.",
        impact: "medium" as const,
        category: "Predictive",
    },
    {
        id: "4",
        title: "Deploy smart power monitoring for UPS devices",
        description: "Loadshedding analysis shows 12% of outages linked to UPS failure. Real-time monitoring enables alerts.",
        impact: "medium" as const,
        category: "Resilience",
    },
]

const defaultTableData = [
    { id: "1", deviceId: "ONT-6134", type: "ONT", region: "Cape Town", rxPower: "-29.1 dBm", temp: "58°C", status: "Critical", lastSeen: "3 min ago" },
    { id: "2", deviceId: "ONT-1156", type: "ONT", region: "Cape Town", rxPower: "-28.5 dBm", temp: "55°C", status: "Critical", lastSeen: "5 min ago" },
    { id: "3", deviceId: "ONT-7801", type: "ONT", region: "Pretoria", rxPower: "-27.8 dBm", temp: "50°C", status: "Warning", lastSeen: "2 min ago" },
    { id: "4", deviceId: "ONT-2847", type: "ONT", region: "Cape Town", rxPower: "-27.2 dBm", temp: "52°C", status: "Warning", lastSeen: "8 min ago" },
    { id: "5", deviceId: "ONT-3912", type: "ONT", region: "JHB South", rxPower: "-26.8 dBm", temp: "48°C", status: "Warning", lastSeen: "1 min ago" },
    { id: "6", deviceId: "ONT-4290", type: "ONT", region: "JHB North", rxPower: "-26.2 dBm", temp: "46°C", status: "Warning", lastSeen: "4 min ago" },
    { id: "7", deviceId: "ONT-5423", type: "ONT", region: "Durban", rxPower: "-25.9 dBm", temp: "44°C", status: "Elevated", lastSeen: "2 min ago" },
    { id: "8", deviceId: "ONT-8876", type: "ONT", region: "Polokwane", rxPower: "-25.5 dBm", temp: "42°C", status: "Elevated", lastSeen: "6 min ago" },
]

const tableColumns = [
    { key: "deviceId", label: "Device ID" },
    { key: "type", label: "Type" },
    { key: "region", label: "Region" },
    { key: "rxPower", label: "RX Power" },
    { key: "temp", label: "Temperature" },
    { key: "status", label: "Status" },
    { key: "lastSeen", label: "Last Seen" },
]

const SIGNAL_COLORS = ["#4ade80", "#60a5fa", "#eab308", "#f97316", "#ef4444"]

export function IoTModule() {
    const { data } = useModuleData("iot", {
        flashcardKPIs: defaultFlashcardKPIs,
        activities: defaultActivities,
        issues: defaultIssues,
        tasks: defaultTasks,
        aiRecommendations: defaultAIRecommendations,
        tableData: defaultTableData,
    })

    const flashcardKPIs = (data.flashcardKPIs ?? defaultFlashcardKPIs).map(
        (kpi: (typeof defaultFlashcardKPIs)[number]) => ({
            ...kpi,
            icon: iotKpiIconMap[kpi.iconKey] || <Radio className="h-5 w-5 text-primary" />,
        }),
    )

    return (
        <ModuleLayout
            title="IoT & Device Management"
            flashcardKPIs={flashcardKPIs}
            activities={data.activities ?? defaultActivities}
            issues={data.issues ?? defaultIssues}
            summary="Monitoring 8,670 devices across all regions with 98.4% online rate. Proactive signal analysis identified 24 at-risk ONTs with 7 in critical state (< -28dBm). 5 auto-generated maintenance tickets dispatched for Cape Town Site B. Remote diagnostics reducing truck rolls by 22% this quarter. Firmware updates pending for 340 routers—scheduled for overnight rollout to minimize customer impact."
            tasks={data.tasks ?? defaultTasks}
            aiRecommendations={data.aiRecommendations ?? defaultAIRecommendations}
            tableData={data.tableData ?? defaultTableData}
            tableColumns={tableColumns}
        >
            <div className="grid gap-6 lg:grid-cols-2">
                {/* Signal Health Distribution */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Signal Health Distribution</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <PieChart>
                            <Pie
                                data={defaultSignalHealthData}
                                cx="50%"
                                cy="50%"
                                innerRadius={60}
                                outerRadius={100}
                                paddingAngle={3}
                                dataKey="value"
                                label={({ name, value }) => `${value}`}
                            >
                                {defaultSignalHealthData.map((entry, index) => (
                                    <Cell key={`cell-${index}`} fill={SIGNAL_COLORS[index % SIGNAL_COLORS.length]} />
                                ))}
                            </Pie>
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                        </PieChart>
                    </ResponsiveContainer>
                </div>

                {/* Device Types Online/Offline */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Device Status by Type</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={defaultDeviceTypeData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="type" stroke="#888" fontSize={11} />
                            <YAxis stroke="#888" fontSize={12} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Bar dataKey="online" fill="#4ade80" name="Online" stackId="a" radius={[0, 0, 0, 0]} />
                            <Bar dataKey="offline" fill="#ef4444" name="Offline" stackId="a" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>

                {/* Signal Trend Over Time */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Signal & Alert Trend (24h)</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <AreaChart data={defaultSignalTrendData}>
                            <defs>
                                <linearGradient id="colorSignal" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#60a5fa" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="hour" stroke="#888" fontSize={12} />
                            <YAxis yAxisId="left" stroke="#888" fontSize={12} domain={[-20, -15]} label={{ value: "dBm", angle: -90, position: "insideLeft", style: { fill: "#888" }}} />
                            <YAxis yAxisId="right" orientation="right" stroke="#888" fontSize={12} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Area yAxisId="left" type="monotone" dataKey="avgRx" stroke="#60a5fa" fillOpacity={1} fill="url(#colorSignal)" name="Avg RX (dBm)" />
                            <Line yAxisId="right" type="monotone" dataKey="alerts" stroke="#f97316" strokeWidth={2} dot={{ fill: "#f97316" }} name="Alerts" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>

                {/* Remote Command History */}
                <div className="rounded-xl border border-border bg-card p-6">
                    <h4 className="mb-4 text-sm font-semibold text-foreground">Remote Command History</h4>
                    <ResponsiveContainer width="100%" height={300}>
                        <BarChart data={defaultCommandHistoryData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                            <XAxis dataKey="month" stroke="#888" fontSize={12} />
                            <YAxis stroke="#888" fontSize={12} />
                            <Tooltip
                                contentStyle={{ backgroundColor: "#1a1a2e", border: "1px solid #333", borderRadius: "8px" }}
                            />
                            <Legend />
                            <Bar dataKey="diagnostics" fill="#a855f7" name="Diagnostics" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="reboots" fill="#60a5fa" name="Reboots" radius={[4, 4, 0, 0]} />
                            <Bar dataKey="toggles" fill="#f97316" name="Power Toggles" radius={[4, 4, 0, 0]} />
                        </BarChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </ModuleLayout>
    )
}
