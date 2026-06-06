"use client";

import { useState, useEffect } from "react";
import { useRouter, useLocalSearchParams } from "expo-router";
import {
  ArrowLeft, Play, Zap, AlertTriangle, RotateCcw, CheckCircle,
  Plus, Phone, MapPin, Signal, Thermometer, Wifi,
} from "lucide-react";
import { technicianApi } from "../../../lib/api/client";
import type { TechJob, TechDevice, SpeedTestResult } from "../../../lib/api/types";

// ── Brand Colors ──────────────────────────────────────────────────────

const brandConfig = {
  primary: "#6366f1",
  background: "#0f172a",
  surface: "#1e293b",
  text: "#f8fafc",
  textSecondary: "#94a3b8",
};

// ── Priority Badge ────────────────────────────────────────────────────

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    URGENT: "bg-red-500/20 text-red-400 border border-red-500/30",
    HIGH: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    NORMAL: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
    LOW: "bg-slate-600/60 text-slate-300 border border-slate-500/30",
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${colors[priority] || colors.NORMAL}`}>
      {priority}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    OPEN: "bg-blue-500/20 text-blue-400 border border-blue-500/30",
    IN_PROGRESS: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
    ON_HOLD: "bg-slate-600/60 text-slate-300 border border-slate-500/30",
    CLOSED: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    ESCALATED: "bg-red-500/20 text-red-400 border border-red-500/30",
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${colors[status] || colors.OPEN}`}>
      {status.replace("_", " ")}
    </span>
  );
}

// ── Device Status Card ────────────────────────────────────────────────

function DeviceCard({ device }: { device: TechDevice }) {
  const signalColor =
    device.rx_power_dbm != null
      ? device.rx_power_dbm >= -20
        ? "text-emerald-400"
        : device.rx_power_dbm >= -25
          ? "text-amber-400"
          : "text-red-400"
      : "text-slate-400";

  const statusColor =
    device.status === "ONLINE"
      ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
      : device.status === "OFFLINE"
        ? "bg-red-500/20 text-red-400 border border-red-500/30"
        : "bg-amber-500/20 text-amber-400 border border-amber-500/30";

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 relative">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-slate-100">{device.device_name}</p>
          <p className="text-xs text-slate-400">
            {device.device_type} • {device.serial_number || device.mac_address || "No serial"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${statusColor}`}>
            {device.status}
          </span>
          {device.status === "ONLINE" && (
            <button
              className="h-7 w-7 flex items-center justify-center rounded-lg active:bg-slate-700"
              onClick={(e) => {
                e.stopPropagation();
                technicianApi.rebootDevice(device.id);
              }}
            >
              <RotateCcw className="h-3.5 w-3.5 text-slate-400" />
            </button>
          )}
        </div>
      </div>
      {device.rx_power_dbm != null && (
        <div className="grid grid-cols-3 gap-2 mt-2">
          <div className="text-center bg-slate-700/40 rounded p-1.5">
            <Signal className={`h-3 w-3 mx-auto mb-0.5 ${signalColor}`} />
            <p className={`text-xs font-mono font-bold ${signalColor}`}>{device.rx_power_dbm} dBm</p>
            <p className="text-[9px] text-slate-400">RX</p>
          </div>
          <div className="text-center bg-slate-700/40 rounded p-1.5">
            <Thermometer className="h-3 w-3 mx-auto mb-0.5 text-blue-400" />
            <p className="text-xs font-mono font-bold text-blue-400">{device.temperature_c}°C</p>
            <p className="text-[9px] text-slate-400">Temp</p>
          </div>
          <div className="text-center bg-slate-700/40 rounded p-1.5">
            <Wifi className="h-3 w-3 mx-auto mb-0.5 text-violet-400" />
            <p className="text-xs font-mono font-bold text-violet-400">{device.tx_power_dbm} dBm</p>
            <p className="text-[9px] text-slate-400">TX</p>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Job Detail Page ───────────────────────────────────────────────────

export default function JobDetailPage() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<TechJob | null>(null);
  const [devices, setDevices] = useState<TechDevice[]>([]);
  const [notes, setNotes] = useState("");
  const [speedTest, setSpeedTest] = useState<SpeedTestResult | null>(null);
  const [runningSpeed, setRunningSpeed] = useState(false);
  const [partsUsed, setPartsUsed] = useState<Array<{ product_id: string; quantity: number }>>([]);
  const [partSku, setPartSku] = useState("");
  const [partQty, setPartQty] = useState("1");
  const [status, setStatus] = useState("OPEN");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!jobId) return;
    technicianApi
      .getJob(jobId)
      .then((j) => {
        setJob(j);
        setStatus(j.status);
      })
      .catch((e) => console.error("Failed to load job:", e))
      .finally(() => setLoading(false));
  }, [jobId]);

  useEffect(() => {
    if (!job?.customer_id) return;
    technicianApi
      .getCustomerDevices(job.customer_id)
      .then(setDevices)
      .catch(() => {});
  }, [job?.customer_id]);

  const handleStart = async () => {
    if (!jobId) return;
    await technicianApi.startJob(jobId);
    setStatus("IN_PROGRESS");
  };

  const handleSpeedTest = async () => {
    setRunningSpeed(true);
    try {
      const r = await technicianApi.runSpeedTest();
      setSpeedTest(r);
    } catch {
      setSpeedTest({
        download_mbps: 0,
        upload_mbps: 0,
        latency_ms: 0,
        jitter_ms: 0,
        timestamp: new Date().toISOString(),
      });
    } finally {
      setRunningSpeed(false);
    }
  };

  const handleAddPart = () => {
    if (!partSku) return;
    setPartsUsed([...partsUsed, { product_id: partSku, quantity: parseInt(partQty) || 1 }]);
    setPartSku("");
    setPartQty("1");
  };

  const handleRemovePart = (index: number) => {
    setPartsUsed(partsUsed.filter((_, j) => j !== index));
  };

  const handleComplete = async () => {
    if (!jobId) return;
    setSaving(true);
    try {
      await technicianApi.completeJob({
        job_id: jobId,
        resolution_notes: notes,
        parts_used: partsUsed,
        speed_test: speedTest || undefined,
        fcr: true,
      });
      router.back();
    } catch (e) {
      alert("Complete failed: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const handleEscalate = () => {
    if (!jobId) return;
    technicianApi.escalateJob(jobId, "Escalated from mobile");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <p className="text-sm text-slate-400">Loading job...</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <p className="text-sm text-slate-400">Job not found</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <div className="sticky top-0 z-10 bg-slate-900 px-4 pt-12 pb-3 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <button
            className="h-8 w-8 flex items-center justify-center rounded-lg active:bg-slate-800"
            onClick={() => router.back()}
          >
            <ArrowLeft className="h-5 w-5 text-slate-300" />
          </button>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <PriorityBadge priority={job.priority} />
              <StatusBadge status={status} />
            </div>
            <h3 className="font-semibold text-slate-100 mt-1">{job.subject}</h3>
          </div>
        </div>
      </div>

      <div className="px-4 py-4 space-y-4 pb-24">
        {/* Customer info */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-1">
          <p className="font-medium text-sm text-slate-100">{job.customer_name || job.customer_id}</p>
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <Phone className="h-3 w-3" />{job.customer_phone || "N/A"}
            </span>
          </div>
          <p className="text-xs text-slate-400 flex items-center gap-1">
            <MapPin className="h-3 w-3 shrink-0" />{job.customer_address || "N/A"}
          </p>
          {job.external_fno_ref && (
            <p className="text-xs text-slate-400">FNO Ref: {job.external_fno_ref}</p>
          )}
        </div>

        {/* Description */}
        {job.description && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
            <p className="text-xs font-semibold text-slate-400 mb-1">DESCRIPTION</p>
            <p className="text-sm text-slate-200">{job.description}</p>
          </div>
        )}

        {/* Start button (OPEN status) */}
        {status === "OPEN" && (
          <button
            className="w-full bg-indigo-500 hover:bg-indigo-600 active:bg-indigo-700 text-white font-semibold py-3 rounded-lg flex items-center justify-center gap-2"
            onClick={handleStart}
          >
            <Play className="h-4 w-4" /> Start Job
          </button>
        )}

        {/* Action buttons (IN_PROGRESS status) */}
        {status === "IN_PROGRESS" && (
          <div className="grid grid-cols-2 gap-2">
            <button
              className="bg-slate-800 border border-slate-700 text-slate-200 font-semibold py-3 rounded-lg flex items-center justify-center gap-2 active:bg-slate-700"
              onClick={handleSpeedTest}
              disabled={runningSpeed}
            >
              <Zap className="h-4 w-4 text-amber-400" /> {runningSpeed ? "Testing..." : "Speed Test"}
            </button>
            <button
              className="bg-slate-800 border border-slate-700 text-slate-200 font-semibold py-3 rounded-lg flex items-center justify-center gap-2 active:bg-slate-700"
              onClick={handleEscalate}
            >
              <AlertTriangle className="h-4 w-4 text-red-400" /> Escalate
            </button>
          </div>
        )}

        {/* Speed test results */}
        {speedTest && speedTest.download_mbps > 0 && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
            <p className="text-xs font-semibold text-slate-400 mb-2">SPEED TEST RESULTS</p>
            <div className="grid grid-cols-2 gap-2">
              <div className="text-center bg-slate-700/40 rounded p-2">
                <p className="text-lg font-bold text-emerald-400">{speedTest.download_mbps}</p>
                <p className="text-[10px] text-slate-400">Download Mbps</p>
              </div>
              <div className="text-center bg-slate-700/40 rounded p-2">
                <p className="text-lg font-bold text-blue-400">{speedTest.upload_mbps}</p>
                <p className="text-[10px] text-slate-400">Upload Mbps</p>
              </div>
              <div className="text-center bg-slate-700/40 rounded p-2">
                <p className="text-lg font-bold text-violet-400">{speedTest.latency_ms}</p>
                <p className="text-[10px] text-slate-400">Latency ms</p>
              </div>
              <div className="text-center bg-slate-700/40 rounded p-2">
                <p className="text-lg font-bold text-amber-400">{speedTest.jitter_ms}</p>
                <p className="text-[10px] text-slate-400">Jitter ms</p>
              </div>
            </div>
          </div>
        )}

        {/* Devices at site */}
        {devices.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-slate-400 mb-2">
              DEVICES AT SITE ({devices.length})
            </p>
            <div className="space-y-2">
              {devices.map((d) => (
                <DeviceCard key={d.id} device={d} />
              ))}
            </div>
          </div>
        )}

        {/* Parts checkout */}
        {status === "IN_PROGRESS" && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
            <p className="text-xs font-semibold text-slate-400 mb-2">PARTS USED</p>
            <div className="flex gap-2 mb-2">
              <input
                className="flex-1 bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="SKU or product ID"
                value={partSku}
                onChange={(e) => setPartSku(e.target.value)}
              />
              <input
                className="w-16 bg-slate-700 border border-slate-600 rounded-md px-2 py-2 text-sm text-slate-100 text-center focus:outline-none focus:ring-2 focus:ring-indigo-500"
                type="number"
                min={1}
                value={partQty}
                onChange={(e) => setPartQty(e.target.value)}
              />
              <button
                className="bg-indigo-500 hover:bg-indigo-600 text-white px-3 py-2 rounded-md font-semibold active:bg-indigo-700"
                onClick={handleAddPart}
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            {partsUsed.map((p, i) => (
              <div
                key={i}
                className="flex items-center justify-between bg-slate-700/40 rounded p-2 mb-1"
              >
                <span className="text-xs text-slate-200">
                  {p.product_id} × {p.quantity}
                </span>
                <button
                  className="h-6 w-6 flex items-center justify-center rounded text-slate-400 active:bg-slate-600"
                  onClick={() => handleRemovePart(i)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Resolution notes */}
        {status === "IN_PROGRESS" && (
          <div>
            <label className="text-xs font-semibold text-slate-400 block mb-1">
              Resolution Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Describe what was done..."
              className="w-full bg-slate-700 border border-slate-600 rounded-md px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              rows={3}
            />
          </div>
        )}

        {/* Complete button */}
        {status === "IN_PROGRESS" && (
          <button
            className={`w-full font-semibold py-3 rounded-lg flex items-center justify-center gap-2 ${
              saving || !notes
                ? "bg-emerald-600/40 text-emerald-300/60"
                : "bg-emerald-600 hover:bg-emerald-700 text-white active:bg-emerald-800"
            }`}
            onClick={handleComplete}
            disabled={saving || !notes}
          >
            <CheckCircle className="h-4 w-4" /> {saving ? "Completing..." : "Complete Job"}
          </button>
        )}
      </div>
    </div>
  );
}
