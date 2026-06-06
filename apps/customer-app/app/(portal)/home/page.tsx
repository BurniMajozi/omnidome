"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Home, Camera, Thermometer, Droplets, Activity, ChevronDown, ChevronUp,
  Bell, Zap, Shield, Lightbulb, Tv, Speaker, Fan, Lock, Unlock,
  AlertTriangle, CheckCircle, XCircle, Clock, Wifi, WifiOff,
  Play, Pause, RotateCcw, Settings, Eye, Power,
} from "lucide-react";
import brandConfig from "@/config/brand.json";
import { api } from "@/lib/api/client";

// ─── IoT Types ───────────────────────────────────────────────────────────────

interface IoTScene {
  id: string;
  name: string;
  icon?: string;
  description?: string;
  deviceCount: number;
  isActive: boolean;
  createdAt: string;
}

interface IoTCamera {
  id: string;
  name: string;
  roomName: string;
  snapshotUrl: string;
  isOnline: boolean;
  lastMotionAt?: string;
}

interface IoTSensorOverview {
  temperature: { value: number; unit: string; room: string; trend: "up" | "down" | "stable" };
  humidity: { value: number; unit: string; room: string; trend: "up" | "down" | "stable" };
  motion: { detected: boolean; lastDetected: string; room: string };
}

interface IoTRoom {
  id: string;
  name: string;
  icon?: string;
  deviceCount: number;
  devices: Array<{
    id: string;
    name: string;
    type: string;
    status: "online" | "offline" | "unavailable";
    isOn?: boolean;
    attributes?: Record<string, any>;
  }>;
}

interface IoTEvent {
  id: string;
  eventType: string;
  deviceName: string;
  description: string;
  createdAt: string;
}

interface IoTAlert {
  id: string;
  type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  deviceName?: string;
  isRead: boolean;
  createdAt: string;
}

interface IoTDashboardData {
  scenes: IoTScene[];
  cameras: IoTCamera[];
  sensors: IoTSensorOverview;
  rooms: IoTRoom[];
  recentEvents: IoTEvent[];
  alerts: IoTAlert[];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const brand = brandConfig.colors.primary;

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function sceneIcon(name: string) {
  const n = name.toLowerCase();
  if (n.includes("night") || n.includes("sleep")) return "🌙";
  if (n.includes("morning") || n.includes("wake")) return "☀️";
  if (n.includes("away") || n.includes("leave")) return "🚪";
  if (n.includes("home") || n.includes("arrive")) return "🏠";
  if (n.includes("movie") || n.includes("cinema")) return "🎬";
  if (n.includes("party") || n.includes("fun")) return "🎉";
  if (n.includes("work") || n.includes("focus")) return "💼";
  if (n.includes("relax") || n.includes("chill")) return "🛋️";
  return "⚡";
}

function deviceTypeIcon(type: string) {
  const t = type.toLowerCase();
  if (t.includes("light") || t.includes("bulb")) return <Lightbulb size={16} />;
  if (t.includes("camera")) return <Camera size={16} />;
  if (t.includes("tv") || t.includes("television")) return <Tv size={16} />;
  if (t.includes("speaker") || t.includes("audio")) return <Speaker size={16} />;
  if (t.includes("fan")) return <Fan size={16} />;
  if (t.includes("lock")) return <Lock size={16} />;
  if (t.includes("thermostat") || t.includes("temp")) return <Thermometer size={16} />;
  return <Power size={16} />;
}

// ─── Skeleton Loaders ────────────────────────────────────────────────────────

function SkeletonBlock({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-gray-700/50 ${className}`} />;
}

function ScenesSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonBlock className="h-5 w-32" />
      <div className="flex gap-3 overflow-hidden">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonBlock key={i} className="h-24 w-28 shrink-0" />
        ))}
      </div>
    </div>
  );
}

function CamerasSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonBlock className="h-5 w-40" />
      <div className="grid grid-cols-2 gap-3">
        {[1, 2, 3, 4].map((i) => (
          <SkeletonBlock key={i} className="h-32 w-full" />
        ))}
      </div>
    </div>
  );
}

function SensorsSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonBlock className="h-5 w-36" />
      <div className="grid grid-cols-3 gap-3">
        {[1, 2, 3].map((i) => (
          <SkeletonBlock key={i} className="h-24 w-full" />
        ))}
      </div>
    </div>
  );
}

// ─── Section Components ──────────────────────────────────────────────────────

function ActiveAlertsBanner({ alerts }: { alerts: IoTAlert[] }) {
  const critical = alerts.filter((a) => a.severity === "critical");
  const warnings = alerts.filter((a) => a.severity === "warning");
  const infos = alerts.filter((a) => a.severity === "info");

  if (alerts.length === 0) return null;

  return (
    <div className="space-y-2">
      {critical.map((alert) => (
        <div
          key={alert.id}
          className="flex items-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3"
        >
          <XCircle size={20} className="shrink-0 text-red-400" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-red-300">{alert.title}</p>
            <p className="text-xs text-red-400/70 truncate">{alert.message}</p>
          </div>
          <span className="text-xs text-red-400/50 shrink-0">{timeAgo(alert.createdAt)}</span>
        </div>
      ))}
      {warnings.map((alert) => (
        <div
          key={alert.id}
          className="flex items-center gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3"
        >
          <AlertTriangle size={20} className="shrink-0 text-amber-400" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-amber-300">{alert.title}</p>
            <p className="text-xs text-amber-400/70 truncate">{alert.message}</p>
          </div>
          <span className="text-xs text-amber-400/50 shrink-0">{timeAgo(alert.createdAt)}</span>
        </div>
      ))}
      {infos.map((alert) => (
        <div
          key={alert.id}
          className="flex items-center gap-3 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3"
        >
          <Bell size={20} className="shrink-0 text-blue-400" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-blue-300">{alert.title}</p>
            <p className="text-xs text-blue-400/70 truncate">{alert.message}</p>
          </div>
          <span className="text-xs text-blue-400/50 shrink-0">{timeAgo(alert.createdAt)}</span>
        </div>
      ))}
    </div>
  );
}

function QuickScenes({
  scenes,
  activatingId,
  onActivate,
}: {
  scenes: IoTScene[];
  activatingId: string | null;
  onActivate: (id: string) => void;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Zap size={18} style={{ color: brand }} />
        Quick Scenes
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide -mx-4 px-4 lg:mx-0 lg:px-0">
        {scenes.map((scene) => (
          <button
            key={scene.id}
            onClick={() => onActivate(scene.id)}
            disabled={activatingId === scene.id}
            className={`shrink-0 w-28 rounded-2xl p-4 text-center transition-all duration-200 border ${
              scene.isActive
                ? "border-transparent shadow-lg"
                : "border-gray-700 bg-gray-800/60 hover:bg-gray-800 hover:border-gray-600"
            } ${activatingId === scene.id ? "opacity-60" : ""}`}
            style={
              scene.isActive
                ? { backgroundColor: `${brand}20`, borderColor: `${brand}50`, boxShadow: `0 0 20px ${brand}15` }
                : undefined
            }
          >
            <div className="text-2xl mb-2">{sceneIcon(scene.name)}</div>
            <p className="text-xs font-medium text-white truncate">{scene.name}</p>
            <p className="text-[10px] text-gray-400 mt-0.5">{scene.deviceCount} devices</p>
            {activatingId === scene.id && (
              <div className="mt-1 flex justify-center">
                <RotateCcw size={12} className="animate-spin text-gray-400" />
              </div>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

function FavoriteCameras({ cameras }: { cameras: IoTCamera[] }) {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Camera size={18} style={{ color: brand }} />
        Favorite Cameras
      </h2>
      <div className="grid grid-cols-2 gap-3">
        {cameras.map((cam) => (
          <div
            key={cam.id}
            className="relative rounded-2xl overflow-hidden bg-gray-800 border border-gray-700 group"
          >
            {/* Snapshot placeholder */}
            <div className="aspect-video bg-gradient-to-br from-gray-700 to-gray-800 flex items-center justify-center relative">
              {cam.isOnline ? (
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <Camera size={28} className="text-gray-500 mb-1" />
                  <span className="text-[10px] text-gray-500 font-medium">{cam.name}</span>
                  {/* Simulated camera feed overlay */}
                  <div className="absolute top-2 left-2 flex items-center gap-1">
                    <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                    <span className="text-[9px] text-red-400 font-medium">LIVE</span>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center">
                  <WifiOff size={24} className="text-gray-600 mb-1" />
                  <span className="text-[10px] text-gray-600">Offline</span>
                </div>
              )}
              {/* Hover overlay */}
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
                <Eye size={20} className="text-white" />
              </div>
            </div>
            {/* Info bar */}
            <div className="px-3 py-2 flex items-center justify-between">
              <div className="min-w-0">
                <p className="text-xs font-medium text-white truncate">{cam.name}</p>
                <p className="text-[10px] text-gray-400">{cam.roomName}</p>
              </div>
              <div className={`w-2 h-2 rounded-full shrink-0 ${cam.isOnline ? "bg-green-500" : "bg-gray-600"}`} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function SensorOverview({ sensors }: { sensors: IoTSensorOverview }) {
  const trendIcon = (trend: string) => {
    if (trend === "up") return "↑";
    if (trend === "down") return "↓";
    return "→";
  };
  const trendColor = (trend: string) => {
    if (trend === "up") return "text-red-400";
    if (trend === "down") return "text-blue-400";
    return "text-gray-400";
  };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Activity size={18} style={{ color: brand }} />
        Sensor Overview
      </h2>
      <div className="grid grid-cols-3 gap-3">
        {/* Temperature */}
        <div className="rounded-2xl bg-gray-800/60 border border-gray-700 p-4 text-center">
          <div className="flex items-center justify-center mb-2">
            <Thermometer size={20} className="text-orange-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {sensors.temperature.value}
            <span className="text-sm text-gray-400">°{sensors.temperature.unit === "C" ? "C" : "F"}</span>
          </p>
          <p className="text-[10px] text-gray-400 mt-1">Temperature</p>
          <div className="flex items-center justify-center gap-1 mt-1">
            <span className={`text-xs ${trendColor(sensors.temperature.trend)}`}>
              {trendIcon(sensors.temperature.trend)}
            </span>
            <span className="text-[10px] text-gray-500">{sensors.temperature.room}</span>
          </div>
        </div>

        {/* Humidity */}
        <div className="rounded-2xl bg-gray-800/60 border border-gray-700 p-4 text-center">
          <div className="flex items-center justify-center mb-2">
            <Droplets size={20} className="text-cyan-400" />
          </div>
          <p className="text-2xl font-bold text-white">
            {sensors.humidity.value}
            <span className="text-sm text-gray-400">%</span>
          </p>
          <p className="text-[10px] text-gray-400 mt-1">Humidity</p>
          <div className="flex items-center justify-center gap-1 mt-1">
            <span className={`text-xs ${trendColor(sensors.humidity.trend)}`}>
              {trendIcon(sensors.humidity.trend)}
            </span>
            <span className="text-[10px] text-gray-500">{sensors.humidity.room}</span>
          </div>
        </div>

        {/* Motion */}
        <div className="rounded-2xl bg-gray-800/60 border border-gray-700 p-4 text-center">
          <div className="flex items-center justify-center mb-2">
            <Shield size={20} className={sensors.motion.detected ? "text-green-400" : "text-gray-500"} />
          </div>
          <p className={`text-lg font-bold ${sensors.motion.detected ? "text-green-400" : "text-gray-400"}`}>
            {sensors.motion.detected ? "Detected" : "Clear"}
          </p>
          <p className="text-[10px] text-gray-400 mt-1">Motion</p>
          <div className="flex items-center justify-center gap-1 mt-1">
            <Clock size={10} className="text-gray-500" />
            <span className="text-[10px] text-gray-500">
              {sensors.motion.detected ? timeAgo(sensors.motion.lastDetected) : "No activity"}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function DeviceRooms({ rooms }: { rooms: IoTRoom[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Home size={18} style={{ color: brand }} />
        Device Rooms
      </h2>
      <div className="space-y-2">
        {rooms.map((room) => {
          const isExpanded = expandedId === room.id;
          const onlineCount = room.devices.filter((d) => d.status === "online").length;
          return (
            <div
              key={room.id}
              className="rounded-2xl bg-gray-800/60 border border-gray-700 overflow-hidden"
            >
              <button
                onClick={() => setExpandedId(isExpanded ? null : room.id)}
                className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-800/80 transition-colors"
              >
                <div
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-lg"
                  style={{ backgroundColor: `${brand}20` }}
                >
                  {room.icon || "🏠"}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white">{room.name}</p>
                  <p className="text-[10px] text-gray-400">
                    {room.deviceCount} devices · {onlineCount} online
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1">
                    <Wifi size={12} className="text-green-400" />
                    <span className="text-xs text-green-400">{onlineCount}</span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp size={16} className="text-gray-400" />
                  ) : (
                    <ChevronDown size={16} className="text-gray-400" />
                  )}
                </div>
              </button>
              {isExpanded && (
                <div className="border-t border-gray-700/50 px-4 py-2 space-y-1">
                  {room.devices.map((device) => (
                    <div
                      key={device.id}
                      className="flex items-center gap-3 py-2 px-2 rounded-lg hover:bg-gray-700/30"
                    >
                      <div className={`p-1.5 rounded-md ${device.status === "online" ? "bg-gray-700" : "bg-gray-800"}`}>
                        <span className={device.status === "online" ? "text-gray-300" : "text-gray-600"}>
                          {deviceTypeIcon(device.type)}
                        </span>
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium text-white truncate">{device.name}</p>
                        <p className="text-[10px] text-gray-500 capitalize">{device.type}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        {device.isOn !== undefined && (
                          <span
                            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                              device.isOn ? "bg-green-500/20 text-green-400" : "bg-gray-700 text-gray-500"
                            }`}
                          >
                            {device.isOn ? "ON" : "OFF"}
                          </span>
                        )}
                        <div
                          className={`w-2 h-2 rounded-full ${
                            device.status === "online"
                              ? "bg-green-500"
                              : device.status === "offline"
                              ? "bg-gray-600"
                              : "bg-red-500"
                          }`}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function RecentEvents({ events }: { events: IoTEvent[] }) {
  const eventIcon = (type: string) => {
    const t = type.toLowerCase();
    if (t.includes("motion")) return <Shield size={14} className="text-green-400" />;
    if (t.includes("door") || t.includes("lock")) return <Lock size={14} className="text-amber-400" />;
    if (t.includes("light")) return <Lightbulb size={14} className="text-yellow-400" />;
    if (t.includes("temp")) return <Thermometer size={14} className="text-orange-400" />;
    if (t.includes("camera")) return <Camera size={14} className="text-blue-400" />;
    return <Activity size={14} className="text-gray-400" />;
  };

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2">
        <Clock size={18} style={{ color: brand }} />
        Recent Events
      </h2>
      <div className="space-y-1">
        {events.slice(0, 5).map((event) => (
          <div
            key={event.id}
            className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-gray-800/40 border border-gray-700/50"
          >
            <div className="p-1.5 rounded-lg bg-gray-700/50">{eventIcon(event.eventType)}</div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-white truncate">{event.description}</p>
              <p className="text-[10px] text-gray-500">{event.deviceName}</p>
            </div>
            <span className="text-[10px] text-gray-500 shrink-0">{timeAgo(event.createdAt)}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// ─── Mock Data Fallback ───────────────────────────────────────────────────────

function getMockData(): IoTDashboardData {
  return {
    scenes: [
      { id: "s1", name: "Good Morning", icon: "☀️", description: "Turn on lights, adjust thermostat", deviceCount: 6, isActive: false, createdAt: "2026-01-01T00:00:00Z" },
      { id: "s2", name: "Night Mode", icon: "🌙", description: "Dim lights, lock doors, arm cameras", deviceCount: 12, isActive: true, createdAt: "2026-01-01T00:00:00Z" },
      { id: "s3", name: "Away", icon: "🚪", description: "Turn off all, enable security", deviceCount: 15, isActive: false, createdAt: "2026-01-01T00:00:00Z" },
      { id: "s4", name: "Movie Time", icon: "🎬", description: "Dim lights, turn on TV & sound", deviceCount: 5, isActive: false, createdAt: "2026-01-01T00:00:00Z" },
      { id: "s5", name: "Work Focus", icon: "💼", description: "Office lights on, quiet mode", deviceCount: 4, isActive: false, createdAt: "2026-01-01T00:00:00Z" },
    ],
    cameras: [
      { id: "c1", name: "Front Door", roomName: "Entrance", snapshotUrl: "", isOnline: true, lastMotionAt: new Date(Date.now() - 120000).toISOString() },
      { id: "c2", name: "Living Room", roomName: "Living Room", snapshotUrl: "", isOnline: true },
      { id: "c3", name: "Backyard", roomName: "Garden", snapshotUrl: "", isOnline: false },
      { id: "c4", name: "Garage", roomName: "Garage", snapshotUrl: "", isOnline: true, lastMotionAt: new Date(Date.now() - 3600000).toISOString() },
    ],
    sensors: {
      temperature: { value: 23, unit: "C", room: "Living Room", trend: "stable" },
      humidity: { value: 52, unit: "%", room: "Bedroom", trend: "down" },
      motion: { detected: false, lastDetected: new Date(Date.now() - 7200000).toISOString(), room: "Entrance" },
    },
    rooms: [
      {
        id: "r1", name: "Living Room", icon: "🛋️", deviceCount: 8,
        devices: [
          { id: "d1", name: "Ceiling Light", type: "light", status: "online", isOn: true },
          { id: "d2", name: "Smart TV", type: "television", status: "online", isOn: false },
          { id: "d3", name: "Soundbar", type: "speaker", status: "online", isOn: false },
          { id: "d4", name: "Thermostat", type: "thermostat", status: "online" },
          { id: "d5", name: "Living Room Cam", type: "camera", status: "online" },
          { id: "d6", name: "Floor Lamp", type: "light", status: "online", isOn: true },
          { id: "d7", name: "Smart Fan", type: "fan", status: "offline" },
          { id: "d8", name: "Motion Sensor", type: "sensor", status: "online" },
        ],
      },
      {
        id: "r2", name: "Kitchen", icon: "🍳", deviceCount: 5,
        devices: [
          { id: "d9", name: "Kitchen Light", type: "light", status: "online", isOn: false },
          { id: "d10", name: "Smart Fridge", type: "appliance", status: "online" },
          { id: "d11", name: "Smoke Detector", type: "sensor", status: "online" },
          { id: "d12", name: "Kitchen Cam", type: "camera", status: "online" },
          { id: "d13", name: "Smart Plug", type: "plug", status: "offline" },
        ],
      },
      {
        id: "r3", name: "Bedroom", icon: "🛏️", deviceCount: 4,
        devices: [
          { id: "d14", name: "Bedside Lamp L", type: "light", status: "online", isOn: true },
          { id: "d15", name: "Bedside Lamp R", type: "light", status: "online", isOn: false },
          { id: "d16", name: "Bedroom Sensor", type: "sensor", status: "online" },
          { id: "d17", name: "Smart Blinds", type: "blind", status: "online", isOn: true },
        ],
      },
      {
        id: "r4", name: "Entrance", icon: "🚪", deviceCount: 3,
        devices: [
          { id: "d18", name: "Porch Light", type: "light", status: "online", isOn: true },
          { id: "d19", name: "Front Door Lock", type: "lock", status: "online", isOn: true },
          { id: "d20", name: "Doorbell Cam", type: "camera", status: "online" },
        ],
      },
      {
        id: "r5", name: "Garage", icon: "🚗", deviceCount: 3,
        devices: [
          { id: "d21", name: "Garage Light", type: "light", status: "offline" },
          { id: "d22", name: "Garage Door", type: "lock", status: "online", isOn: false },
          { id: "d23", name: "Garage Cam", type: "camera", status: "online" },
        ],
      },
    ],
    recentEvents: [
      { id: "e1", eventType: "motion", deviceName: "Front Door Cam", description: "Motion detected at front door", createdAt: new Date(Date.now() - 120000).toISOString() },
      { id: "e2", eventType: "light", deviceName: "Ceiling Light", description: "Living room light turned on", createdAt: new Date(Date.now() - 600000).toISOString() },
      { id: "e3", eventType: "lock", deviceName: "Front Door Lock", description: "Front door locked automatically", createdAt: new Date(Date.now() - 1800000).toISOString() },
      { id: "e4", eventType: "temperature", deviceName: "Thermostat", description: "Temperature adjusted to 23°C", createdAt: new Date(Date.now() - 3600000).toISOString() },
      { id: "e5", eventType: "camera", deviceName: "Backyard Cam", description: "Camera went offline", createdAt: new Date(Date.now() - 7200000).toISOString() },
    ],
    alerts: [
      { id: "a1", type: "device_offline", severity: "warning", title: "Camera Offline", message: "Backyard camera has been offline for 2 hours", deviceName: "Backyard Cam", isRead: false, createdAt: new Date(Date.now() - 7200000).toISOString() },
      { id: "a2", type: "motion", severity: "info", title: "Motion Detected", message: "Motion detected at front door", deviceName: "Front Door Cam", isRead: false, createdAt: new Date(Date.now() - 120000).toISOString() },
    ],
  };
}

// ─── Main Page Component ─────────────────────────────────────────────────────

export default function SmartHomePage() {
  const [data, setData] = useState<IoTDashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activatingSceneId, setActivatingSceneId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      // Attempt to fetch from the IoT dashboard API
      // Falls back to mock data if the endpoint is unavailable
      try {
        const result = await api.request<IoTDashboardData>("/portal/iot/dashboard");
        setData(result);
      } catch {
        // API not available — use mock data for development
        setData(getMockData());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleActivateScene = useCallback(async (sceneId: string) => {
    setActivatingSceneId(sceneId);
    try {
      await api.request(`/portal/iot/scenes/${sceneId}/activate`, { method: "POST" });
      // Optimistically update local state
      setData((prev) =>
        prev
          ? {
              ...prev,
              scenes: prev.scenes.map((s) => ({
                ...s,
                isActive: s.id === sceneId,
              })),
            }
          : prev
      );
    } catch {
      // Scene activation failed — could show toast notification
    } finally {
      setActivatingSceneId(null);
    }
  }, []);

  // ── Loading State ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-900 p-4 lg:p-6 space-y-8 max-w-5xl mx-auto">
        <div className="space-y-1">
          <SkeletonBlock className="h-7 w-48" />
          <SkeletonBlock className="h-4 w-64" />
        </div>
        <ActiveAlertsBanner alerts={[]} />
        <ScenesSkeleton />
        <CamerasSkeleton />
        <SensorsSkeleton />
        <div className="space-y-3">
          <SkeletonBlock className="h-5 w-36" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
          <SkeletonBlock className="h-16 w-full" />
        </div>
      </div>
    );
  }

  // ── Error State ─────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="text-center space-y-4 max-w-md">
          <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
            <XCircle size={32} className="text-red-400" />
          </div>
          <h2 className="text-xl font-semibold text-white">Something went wrong</h2>
          <p className="text-sm text-gray-400">{error}</p>
          <button
            onClick={fetchData}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-colors"
            style={{ backgroundColor: brand }}
          >
            <RotateCcw size={14} />
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  // ── Loaded State ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-gray-900">
      <div className="p-4 lg:p-6 max-w-5xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Home size={24} style={{ color: brand }} />
              Smart Home
            </h1>
            <p className="text-sm text-gray-400 mt-1">Monitor and control your connected devices</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchData}
              className="p-2 rounded-xl bg-gray-800 border border-gray-700 hover:bg-gray-700 transition-colors"
              aria-label="Refresh"
            >
              <RotateCcw size={16} className="text-gray-400" />
            </button>
            <button
              className="p-2 rounded-xl bg-gray-800 border border-gray-700 hover:bg-gray-700 transition-colors"
              aria-label="Settings"
            >
              <Settings size={16} className="text-gray-400" />
            </button>
          </div>
        </div>

        {/* 1. Active Alerts Banner */}
        <ActiveAlertsBanner alerts={data.alerts} />

        {/* 2. Quick Scenes — Horizontal Scroll */}
        <QuickScenes
          scenes={data.scenes}
          activatingId={activatingSceneId}
          onActivate={handleActivateScene}
        />

        {/* 3. Favorite Cameras — Grid */}
        <FavoriteCameras cameras={data.cameras} />

        {/* 4. Sensor Overview */}
        <SensorOverview sensors={data.sensors} />

        {/* 5. Device Rooms — Accordion */}
        <DeviceRooms rooms={data.rooms} />

        {/* 6. Recent Events — Last 5 */}
        <RecentEvents events={data.recentEvents} />

        {/* Bottom spacer for mobile nav */}
        <div className="h-8" />
      </div>
    </div>
  );
}
