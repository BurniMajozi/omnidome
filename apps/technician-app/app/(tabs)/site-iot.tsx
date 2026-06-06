"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Cpu, Wifi, WifiOff, Battery, BatteryLow, BatteryMedium, BatteryFull,
  Camera, Thermometer, Droplets, Lock, Unlock, Zap, RefreshCw,
  CheckSquare, Square, Signal, Clock, MapPin, ChevronRight,
  Activity, Play, CheckCircle2, AlertTriangle, Loader2,
} from "lucide-react";

// ── Types ──────────────────────────────────────────────────────────────

interface IoTDevice {
  id: string;
  name: string;
  type: "camera" | "sensor" | "smartlock" | "gateway" | "thermostat";
  room: string;
  status: "online" | "offline" | "warning";
  battery?: number;
  signal?: number;
  lastSeen: string;
  readings?: Record<string, string | number>;
  snapshot?: string;
}

interface SensorReading {
  id: string;
  device: string;
  metric: string;
  value: string;
  unit: string;
  timestamp: string;
  status: "normal" | "warning" | "critical";
}

interface ChecklistItem {
  id: string;
  label: string;
  checked: boolean;
}

// ── Mock Data ──────────────────────────────────────────────────────────

const MOCK_DEVICES: IoTDevice[] = [
  {
    id: "gw-001", name: "Main Gateway", type: "gateway", room: "Living Room",
    status: "online", battery: undefined, signal: 95, lastSeen: "Just now",
    readings: { "Connected Devices": 12 },
  },
  {
    id: "cam-001", name: "Front Door Camera", type: "camera", room: "Entrance",
    status: "online", battery: 78, signal: 82, lastSeen: "2 min ago",
  },
  {
    id: "cam-002", name: "Backyard Camera", type: "camera", room: "Garden",
    status: "online", battery: 45, signal: 61, lastSeen: "1 min ago",
  },
  {
    id: "cam-003", name: "Garage Camera", type: "camera", room: "Garage",
    status: "offline", battery: 12, signal: 0, lastSeen: "3 hours ago",
  },
  {
    id: "sens-001", name: "Motion Sensor", type: "sensor", room: "Hallway",
    status: "online", battery: 92, signal: 88, lastSeen: "30 sec ago",
    readings: { Motion: "Clear", Temperature: "22°C" },
  },
  {
    id: "sens-002", name: "Window Sensor", type: "sensor", room: "Bedroom",
    status: "online", battery: 67, signal: 74, lastSeen: "5 min ago",
    readings: { State: "Closed", Temperature: "21°C" },
  },
  {
    id: "sens-003", name: "Smoke Detector", type: "sensor", room: "Kitchen",
    status: "warning", battery: 23, signal: 55, lastSeen: "10 min ago",
    readings: { Smoke: "Clear", CO: "0 ppm" },
  },
  {
    id: "lock-001", name: "Front Door Lock", type: "smartlock", room: "Entrance",
    status: "online", battery: 84, signal: 90, lastSeen: "Just now",
    readings: { State: "Locked", "Last User": "Homeowner" },
  },
  {
    id: "lock-002", name: "Side Gate Lock", type: "smartlock", room: "Garden",
    status: "offline", battery: 5, signal: 0, lastSeen: "1 day ago",
    readings: { State: "Unknown" },
  },
  {
    id: "therm-001", name: "Smart Thermostat", type: "thermostat", room: "Living Room",
    status: "online", battery: undefined, signal: 91, lastSeen: "Just now",
    readings: { Temperature: "22°C", Humidity: "45%", Target: "21°C" },
  },
];

const MOCK_SENSOR_READINGS: SensorReading[] = [
  { id: "r1", device: "Motion Sensor", metric: "Motion", value: "Clear", unit: "", timestamp: "14:32", status: "normal" },
  { id: "r2", device: "Thermostat", metric: "Temperature", value: "22.3", unit: "°C", timestamp: "14:31", status: "normal" },
  { id: "r3", device: "Thermostat", metric: "Humidity", value: "45", unit: "%", timestamp: "14:31", status: "normal" },
  { id: "r4", device: "Smoke Detector", metric: "Smoke Level", value: "0.02", unit: "%", timestamp: "14:30", status: "normal" },
  { id: "r5", device: "Smoke Detector", metric: "Battery", value: "23", unit: "%", timestamp: "14:30", status: "warning" },
  { id: "r6", device: "Window Sensor", metric: "State", value: "Closed", unit: "", timestamp: "14:28", status: "normal" },
  { id: "r7", device: "Garage Camera", metric: "Battery", value: "12", unit: "%", timestamp: "11:15", status: "critical" },
  { id: "r8", device: "Side Gate Lock", metric: "Battery", value: "5", unit: "%", timestamp: "Yesterday", status: "critical" },
  { id: "r9", device: "Front Door Lock", metric: "Access Events", value: "3", unit: "", timestamp: "14:20", status: "normal" },
  { id: "r10", device: "Gateway", metric: "Uptime", value: "99.8", unit: "%", timestamp: "14:32", status: "normal" },
];

const INITIAL_CHECKLIST: ChecklistItem[] = [
  { id: "c1", label: "Gateway powered on and connected", checked: false },
  { id: "c2", label: "All cameras mounted and angled", checked: false },
  { id: "c3", label: "Motion sensors paired and tested", checked: false },
  { id: "c4", label: "Door/window sensors installed", checked: false },
  { id: "c5", label: "Smart locks calibrated", checked: false },
  { id: "c6", label: "Thermostat connected to HVAC", checked: false },
  { id: "c7", label: "Smoke detectors tested", checked: false },
  { id: "c8", label: "All devices reporting to cloud", checked: false },
  { id: "c9", label: "Customer app paired with gateway", checked: false },
  { id: "c10", label: "Walkthrough completed with customer", checked: false },
];

// ── Helpers ────────────────────────────────────────────────────────────

function getBatteryIcon(level?: number) {
  if (level === undefined) return null;
  if (level <= 15) return <BatteryLow className="h-3.5 w-3.5 text-red-400" />;
  if (level <= 40) return <BatteryMedium className="h-3.5 w-3.5 text-amber-400" />;
  if (level <= 70) return <Battery className="h-3.5 w-3.5 text-yellow-400" />;
  return <BatteryFull className="h-3.5 w-3.5 text-emerald-400" />;
}

function getDeviceIcon(type: IoTDevice["type"]) {
  switch (type) {
    case "camera": return <Camera className="h-4 w-4" />;
    case "sensor": return <Activity className="h-4 w-4" />;
    case "smartlock": return <Lock className="h-4 w-4" />;
    case "gateway": return <Cpu className="h-4 w-4" />;
    case "thermostat": return <Thermometer className="h-4 w-4" />;
  }
}

function getStatusColor(status: IoTDevice["status"]) {
  switch (status) {
    case "online": return "bg-emerald-500";
    case "offline": return "bg-red-500";
    case "warning": return "bg-amber-500";
  }
}

function getStatusText(status: IoTDevice["status"]) {
  switch (status) {
    case "online": return "text-emerald-400";
    case "offline": return "text-red-400";
    case "warning": return "text-amber-400";
  }
}

function getReadingStatusColor(status: SensorReading["status"]) {
  switch (status) {
    case "normal": return "text-emerald-400";
    case "warning": return "text-amber-400";
    case "critical": return "text-red-400";
  }
}

// ── Section: Device Health Overview ────────────────────────────────────

function HealthOverview({ devices }: { devices: IoTDevice[] }) {
  const online = devices.filter((d) => d.status === "online").length;
  const offline = devices.filter((d) => d.status === "offline").length;
  const warning = devices.filter((d) => d.status === "warning").length;
  const avgBattery = Math.round(
    devices.filter((d) => d.battery !== undefined).reduce((s, d) => s + (d.battery || 0), 0) /
    devices.filter((d) => d.battery !== undefined).length
  );
  const avgSignal = Math.round(
    devices.filter((d) => d.signal !== undefined && d.status !== "offline").reduce((s, d) => s + (d.signal || 0), 0) /
    devices.filter((d) => d.signal !== undefined && d.status !== "offline").length
  );

  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-300 mb-3">Device Health</h2>
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Wifi className="h-4 w-4 text-emerald-400" />
            <span className="text-xs text-slate-400">Online</span>
          </div>
          <p className="text-2xl font-bold text-emerald-400">{online}</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <WifiOff className="h-4 w-4 text-red-400" />
            <span className="text-xs text-slate-400">Offline</span>
          </div>
          <p className="text-2xl font-bold text-red-400">{offline}</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            {getBatteryIcon(avgBattery)}
            <span className="text-xs text-slate-400">Avg Battery</span>
          </div>
          <p className="text-2xl font-bold text-slate-100">{avgBattery}%</p>
        </div>
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="flex items-center gap-2 mb-2">
            <Signal className="h-4 w-4 text-blue-400" />
            <span className="text-xs text-slate-400">Avg Signal</span>
          </div>
          <p className="text-2xl font-bold text-slate-100">{avgSignal}%</p>
        </div>
      </div>
      {warning > 0 && (
        <div className="mt-2 bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
          <p className="text-xs text-amber-300">{warning} device{warning > 1 ? "s" : ""} need attention</p>
        </div>
      )}
    </div>
  );
}

// ── Section: Camera Snapshots Grid ─────────────────────────────────────

function CameraSnapshots({ devices }: { devices: IoTDevice[] }) {
  const cameras = devices.filter((d) => d.type === "camera");

  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-300 mb-3">Camera Snapshots</h2>
      <div className="grid grid-cols-2 gap-2">
        {cameras.map((cam) => (
          <div
            key={cam.id}
            className={`bg-slate-800 border rounded-lg overflow-hidden ${
              cam.status === "offline" ? "border-red-500/30 opacity-60" : "border-slate-700"
            }`}
          >
            {/* Snapshot placeholder */}
            <div className={`h-28 flex items-center justify-center relative ${
              cam.status === "offline"
                ? "bg-slate-700"
                : "bg-gradient-to-br from-slate-700 to-slate-800"
            }`}>
              {cam.status === "offline" ? (
                <div className="text-center">
                  <Camera className="h-6 w-6 text-slate-500 mx-auto mb-1" />
                  <p className="text-[10px] text-slate-500">Offline</p>
                </div>
              ) : (
                <div className="text-center">
                  <Camera className="h-8 w-8 text-slate-500 mx-auto mb-1" />
                  <p className="text-[10px] text-slate-500">Live View</p>
                  <div className="absolute top-1.5 right-1.5 flex items-center gap-1">
                    <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[9px] text-red-400 font-semibold">REC</span>
                  </div>
                </div>
              )}
            </div>
            <div className="p-2">
              <p className="text-xs font-medium text-slate-200 truncate">{cam.name}</p>
              <div className="flex items-center justify-between mt-1">
                <span className="text-[10px] text-slate-400 flex items-center gap-1">
                  <MapPin className="h-2.5 w-2.5" />{cam.room}
                </span>
                <span className={`text-[10px] font-medium ${getStatusText(cam.status)}`}>
                  {cam.status}
                </span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Section: Sensor Readings Table ─────────────────────────────────────

function SensorReadingsTable({ readings }: { readings: SensorReading[] }) {
  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-300 mb-3">Sensor Readings</h2>
      <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
        <div className="grid grid-cols-12 gap-1 px-3 py-2 border-b border-slate-700 bg-slate-800/80">
          <span className="col-span-3 text-[10px] font-semibold text-slate-400 uppercase">Device</span>
          <span className="col-span-2 text-[10px] font-semibold text-slate-400 uppercase">Metric</span>
          <span className="col-span-2 text-[10px] font-semibold text-slate-400 uppercase">Value</span>
          <span className="col-span-3 text-[10px] font-semibold text-slate-400 uppercase">Time</span>
          <span className="col-span-2 text-[10px] font-semibold text-slate-400 uppercase text-right">Status</span>
        </div>
        <div className="max-h-52 overflow-y-auto">
          {readings.map((r) => (
            <div
              key={r.id}
              className="grid grid-cols-12 gap-1 px-3 py-2 border-b border-slate-700/50 last:border-b-0"
            >
              <span className="col-span-3 text-xs text-slate-300 truncate">{r.device}</span>
              <span className="col-span-2 text-xs text-slate-400 truncate">{r.metric}</span>
              <span className="col-span-2 text-xs text-slate-200 font-medium">
                {r.value}{r.unit}
              </span>
              <span className="col-span-3 text-[10px] text-slate-500 flex items-center gap-1">
                <Clock className="h-2.5 w-2.5" />{r.timestamp}
              </span>
              <span className={`col-span-2 text-[10px] font-semibold text-right ${getReadingStatusColor(r.status)}`}>
                {r.status}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Section: Device List by Room ───────────────────────────────────────

function DeviceListByRoom({ devices }: { devices: IoTDevice[] }) {
  const rooms = [...new Set(devices.map((d) => d.room))];

  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-300 mb-3">Devices by Room</h2>
      <div className="space-y-3">
        {rooms.map((room) => {
          const roomDevices = devices.filter((d) => d.room === room);
          const onlineCount = roomDevices.filter((d) => d.status === "online").length;
          return (
            <div key={room} className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <MapPin className="h-3.5 w-3.5 text-slate-400" />
                  <span className="text-xs font-semibold text-slate-200">{room}</span>
                </div>
                <span className="text-[10px] text-slate-400">
                  {onlineCount}/{roomDevices.length} online
                </span>
              </div>
              <div className="divide-y divide-slate-700/50">
                {roomDevices.map((device) => (
                  <div key={device.id} className="px-3 py-2 flex items-center gap-3">
                    <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${
                      device.status === "online"
                        ? "bg-indigo-500/20 text-indigo-400"
                        : device.status === "warning"
                          ? "bg-amber-500/20 text-amber-400"
                          : "bg-slate-700 text-slate-500"
                    }`}>
                      {getDeviceIcon(device.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-slate-200 truncate">{device.name}</p>
                      <p className="text-[10px] text-slate-500">{device.type} · {device.lastSeen}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {getBatteryIcon(device.battery)}
                      {device.signal !== undefined && device.status !== "offline" && (
                        <span className="text-[10px] text-slate-400">{device.signal}%</span>
                      )}
                      <span className={`h-2 w-2 rounded-full ${getStatusColor(device.status)}`} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Section: Installation Checklist ────────────────────────────────────

function InstallationChecklist({
  items,
  onToggle,
}: {
  items: ChecklistItem[];
  onToggle: (id: string) => void;
}) {
  const checkedCount = items.filter((i) => i.checked).length;
  const progress = Math.round((checkedCount / items.length) * 100);

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-300">Installation Checklist</h2>
        <span className="text-xs text-slate-400">{checkedCount}/{items.length}</span>
      </div>
      {/* Progress bar */}
      <div className="w-full bg-slate-700 rounded-full h-1.5 mb-3">
        <div
          className={`h-1.5 rounded-full transition-all duration-300 ${
            progress === 100 ? "bg-emerald-500" : "bg-indigo-500"
          }`}
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-lg divide-y divide-slate-700/50">
        {items.map((item) => (
          <button
            key={item.id}
            className="w-full px-3 py-2.5 flex items-center gap-3 text-left active:bg-slate-700/50"
            onClick={() => onToggle(item.id)}
          >
            {item.checked ? (
              <CheckSquare className="h-4 w-4 text-indigo-400 shrink-0" />
            ) : (
              <Square className="h-4 w-4 text-slate-500 shrink-0" />
            )}
            <span className={`text-xs ${item.checked ? "text-slate-400 line-through" : "text-slate-200"}`}>
              {item.label}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Section: On-Site Diagnostic ────────────────────────────────────────

function DiagnosticPanel() {
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<{ device: string; status: string }[] | null>(null);

  const runDiagnostic = useCallback(() => {
    setRunning(true);
    setResults(null);
    // Simulate diagnostic run
    setTimeout(() => {
      setResults([
        { device: "Main Gateway", status: "Synced" },
        { device: "Front Door Camera", status: "Synced" },
        { device: "Backyard Camera", status: "Synced" },
        { device: "Garage Camera", status: "Failed" },
        { device: "Motion Sensor", status: "Synced" },
        { device: "Window Sensor", status: "Synced" },
        { device: "Smoke Detector", status: "Synced" },
        { device: "Front Door Lock", status: "Synced" },
        { device: "Side Gate Lock", status: "Failed" },
        { device: "Smart Thermostat", status: "Synced" },
      ]);
      setRunning(false);
    }, 2500);
  }, []);

  return (
    <div>
      <h2 className="text-sm font-semibold text-slate-300 mb-3">On-Site Diagnostic</h2>
      <button
        className={`w-full py-3 rounded-lg flex items-center justify-center gap-2 font-semibold text-sm transition-colors ${
          running
            ? "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30"
            : "bg-indigo-500 text-white active:bg-indigo-600"
        }`}
        onClick={runDiagnostic}
        disabled={running}
      >
        {running ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            Syncing All Devices...
          </>
        ) : (
          <>
            <RefreshCw className="h-4 w-4" />
            Sync All Devices
          </>
        )}
      </button>

      {results && (
        <div className="mt-3 bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-slate-700">
            <p className="text-[10px] font-semibold text-slate-400 uppercase">Diagnostic Results</p>
          </div>
          <div className="divide-y divide-slate-700/50 max-h-48 overflow-y-auto">
            {results.map((r, i) => (
              <div key={i} className="px-3 py-2 flex items-center justify-between">
                <span className="text-xs text-slate-300">{r.device}</span>
                <span className={`text-[10px] font-semibold flex items-center gap-1 ${
                  r.status === "Synced" ? "text-emerald-400" : "text-red-400"
                }`}>
                  {r.status === "Synced" ? (
                    <CheckCircle2 className="h-3 w-3" />
                  ) : (
                    <AlertTriangle className="h-3 w-3" />
                  )}
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────

export default function SiteIoTPage() {
  const [devices] = useState<IoTDevice[]>(MOCK_DEVICES);
  const [readings] = useState<SensorReading[]>(MOCK_SENSOR_READINGS);
  const [checklist, setChecklist] = useState<ChecklistItem[]>(INITIAL_CHECKLIST);

  const toggleChecklist = useCallback((id: string) => {
    setChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, checked: !item.checked } : item))
    );
  }, []);

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900 px-4 pt-12 pb-3 border-b border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-100">Site IoT</h1>
            <p className="text-xs text-slate-400 mt-0.5">Monitor and manage on-site devices</p>
          </div>
          <div className="flex items-center gap-1.5">
            <Cpu className="h-5 w-5 text-indigo-400" />
          </div>
        </div>
      </div>

      <div className="px-4 py-4 space-y-6 pb-24">
        {/* a) Device Health Overview */}
        <HealthOverview devices={devices} />

        {/* b) Camera Snapshots Grid */}
        <CameraSnapshots devices={devices} />

        {/* c) Sensor Readings Table */}
        <SensorReadingsTable readings={readings} />

        {/* d) Device List by Room */}
        <DeviceListByRoom devices={devices} />

        {/* e) Installation Checklist */}
        <InstallationChecklist items={checklist} onToggle={toggleChecklist} />

        {/* f) On-Site Diagnostic */}
        <DiagnosticPanel />
      </div>
    </div>
  );
}
