"use client";
import React, { useEffect, useRef, useState } from "react";
import { Sofa, CookingPot, BedDouble, DoorOpen, Zap, LampFloor, Lightbulb, Blinds, Speaker, Thermometer, Droplets, Refrigerator, Battery, Power, Camera, Fan, Plus, X, Play, Pause, ShieldCheck, Monitor } from "lucide-react";
import styles from "./home-dome-theme.module.css";
export type Room = { id: string; name: string; kind: string; source?: string };
export type RoomDevice = { id: string; name: string; domain: string; room: string | null; state: string; attributes: Record<string, string | number>; observed_at: string };
type Call = <T>(path: string, init?: RequestInit) => Promise<T>;
const examples: RoomDevice[] = [
  { id: "demo-floor", name: "Floor lamp", domain: "light", room: "Living room", state: "on", attributes: { brightness: 179 }, observed_at: "" },
  { id: "demo-spots", name: "Spotlights", domain: "light", room: "Living room", state: "on", attributes: { brightness: 125 }, observed_at: "" },
  { id: "demo-bar", name: "Bar lamp", domain: "light", room: "Living room", state: "on", attributes: {}, observed_at: "" },
  { id: "demo-blinds", name: "Blinds", domain: "cover", room: "Living room", state: "open", attributes: { current_position: 100 }, observed_at: "" },
  { id: "demo-nest", name: "Nest mini", domain: "media_player", room: "Living room", state: "playing", attributes: {}, observed_at: "" },
  { id: "demo-living-temp", name: "Room temperature", domain: "sensor", room: "Living room", state: "22.8", attributes: { device_class: "temperature", unit_of_measurement: "°C" }, observed_at: "" },
  { id: "demo-shutter", name: "Shutter", domain: "cover", room: "Kitchen", state: "open", attributes: { current_position: 100 }, observed_at: "" },
  { id: "demo-kitchen-spots", name: "Spotlights", domain: "light", room: "Kitchen", state: "off", attributes: { brightness: 0 }, observed_at: "" },
  { id: "demo-worktop", name: "Worktop", domain: "light", room: "Kitchen", state: "off", attributes: { brightness: 0 }, observed_at: "" },
  { id: "demo-fridge", name: "Fridge", domain: "binary_sensor", room: "Kitchen", state: "off", attributes: { device_class: "door" }, observed_at: "" },
  { id: "demo-audio", name: "Nest Audio", domain: "media_player", room: "Kitchen", state: "idle", attributes: {}, observed_at: "" },
  { id: "demo-bedside", name: "Bedside lamp", domain: "light", room: "Bedroom", state: "off", attributes: { brightness: 0 }, observed_at: "" },
  { id: "demo-bedroom-temp", name: "Temperature", domain: "sensor", room: "Bedroom", state: "21.4", attributes: { device_class: "temperature", unit_of_measurement: "°C" }, observed_at: "" },
  { id: "demo-power", name: "Home power", domain: "sensor", room: "Energy", state: "797.86", attributes: { device_class: "power", unit_of_measurement: "W" }, observed_at: "" },
  { id: "demo-voltage", name: "Voltage", domain: "sensor", room: "Energy", state: "232.19", attributes: { device_class: "voltage", unit_of_measurement: "V" }, observed_at: "" },
  { id: "demo-charge", name: "Last charge", domain: "sensor", room: "Energy", state: "16.3", attributes: { device_class: "energy", unit_of_measurement: "kWh" }, observed_at: "" },
];
export function deviceValue(device: RoomDevice) {
  const attrs = device.attributes;
  if (device.state === "unavailable" || device.state === "unknown") return "Unavailable";
  if (device.domain === "light" && device.state === "on" && typeof attrs.brightness === "number") return Math.round(attrs.brightness / 255 * 100) + "%";
  if (device.domain === "cover" && typeof attrs.current_position === "number") return device.state + " · " + attrs.current_position + "%";
  if (device.domain === "binary_sensor" && attrs.device_class === "door") return device.state === "on" ? "Open" : "Closed";
  return device.state + (attrs.unit_of_measurement ? " " + attrs.unit_of_measurement : "");
}
function roomIcon(name: string, kind = "other") {
  const value = kind === "other" ? name.toLowerCase() : kind;
  return value.includes("living") ? Sofa : value.includes("kitchen") ? CookingPot : value.includes("bed") ? BedDouble : value.includes("energy") ? Zap : DoorOpen;
}
export function controlValue(device: RoomDevice, level: number) {
  if (["unavailable", "unknown"].includes(device.state)) return "Unavailable";
  if (device.domain === "light" && device.state === "off") return "Off";
  if (["light", "cover"].includes(device.domain) && typeof device.attributes[device.domain === "light" ? "brightness" : "current_position"] === "number") return level + "%";
  return deviceValue(device);
}
export function previewUpdate(row: RoomDevice, service: string, data: Record<string, number> = {}): RoomDevice {
  const state = service === "turn_off" || service === "turn_on" && data.brightness_pct === 0 ? "off"
    : service === "close_cover" || service === "set_cover_position" && data.position === 0 ? "closed"
    : service === "open_cover" || service === "set_cover_position" ? "open"
    : service === "media_pause" ? "paused" : service === "media_play" ? "playing" : "on";
  return { ...row, state, attributes: { ...row.attributes,
    ...(data.brightness_pct !== undefined ? { brightness: Math.round(data.brightness_pct * 255 / 100) } : {}),
    ...(data.position !== undefined ? { current_position: data.position } : {}),
    ...(service === "close_cover" ? { current_position: 0 } : service === "open_cover" ? { current_position: 100 } : {}) } };
}
function deviceIcon(row: RoomDevice) {
  if (row.domain === "light") return row.name.toLowerCase().includes("floor") ? LampFloor : Lightbulb;
  if (row.domain === "cover") return Blinds;
  if (row.domain === "media_player") return Speaker;
  if (row.domain === "camera") return Camera;
  if (row.domain === "fan") return Fan;
  if (row.domain === "climate" || row.attributes.device_class === "temperature") return Thermometer;
  if (row.attributes.device_class === "humidity") return Droplets;
  if (row.attributes.device_class === "door") return Refrigerator;
  if (row.attributes.device_class === "energy") return Battery;
  if (row.attributes.device_class === "power" || row.attributes.device_class === "voltage") return Zap;
  return Power;
}
function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className={styles.dialog} aria-label={title} onCancel={close} onClick={event => { if (event.target === ref.current) { const box = ref.current.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close(); } }}><div className={styles.dialogHeader}><h3 className="text-lg font-semibold">{title}</h3><button aria-label="Close" className={styles.action} onClick={close}><X size={18} /></button></div>{children}</dialog>;
}
export default function RoomHome({ homeId, devices, rooms, owner, connected, control, camera, busy, call, changed, openMedia, cameraPreview }: {
  homeId: string; devices: RoomDevice[]; rooms: Room[]; owner: boolean; connected: boolean; control: boolean; camera: boolean; busy: boolean;
  call: Call; changed: () => Promise<void>; openMedia: () => void; cameraPreview: (row: RoomDevice) => React.ReactNode;
}) {
  const [showcase, setShowcase] = useState(devices.length === 0); const [demo, setDemo] = useState(examples);
  const [selected, setSelected] = useState<string | null>(null); const [filter, setFilter] = useState("all"); const [roomFilter, setRoomFilter] = useState("all");
  const [create, setCreate] = useState(false); const [name, setName] = useState(""); const [kind, setKind] = useState("living");
  const [working, setWorking] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [level, setLevel] = useState(0);
  useEffect(() => { if (devices.length) { setShowcase(false); setSelected(null); } }, [devices.length]);
  const source = showcase ? demo : devices;
  const names = Array.from(new Set([...rooms.map(row => row.name), ...source.map(row => row.room || "Unassigned")]));
  const current = source.find(row => row.id === selected);
  const visible = source.filter(row => filter === "all" || row.domain === filter);
  const disabled = working || busy || !showcase && (!control || !connected || current?.state === "unavailable" || current?.state === "unknown");
  const mutate = async (path: string, method: string, body: unknown) => {
    setWorking(true); setError(""); setNotice("");
    try { const result = await call<{ ok?: boolean; message?: string }>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); if (result.ok === false) throw new Error(result.message || "Action failed"); await changed(); setNotice(result.message || "Saved"); return true; }
    catch (e) { setError((e as Error).message); return false; } finally { setWorking(false); }
  };
  const send = async (service: string, data: Record<string, number> = {}) => {
    if (!current || disabled) return;
    if (showcase) {
      setDemo(rows => rows.map(row => row.id === current.id ? previewUpdate(row, service, data) : row));
      setNotice("Showcase updated — no command was sent to a device."); return;
    }
    await mutate("/" + homeId + "/devices/" + current.id + "/control", "POST", { service, service_data: data });
  };
  const open = (row: RoomDevice) => { setSelected(row.id); setError(""); setNotice(""); setLevel(row.domain === "cover" ? Number(row.attributes.current_position || 0) : Math.round(Number(row.attributes.brightness || 0) / 255 * 100)); };
  const temperature = source.find(row => row.attributes.device_class === "temperature");
  const humidity = source.find(row => row.attributes.device_class === "humidity");
  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div className={styles.pills}>{temperature && <span className={styles.pill}><Thermometer size={16} className="text-red-500" />{deviceValue(temperature)}</span>}{humidity && <span className={styles.pill}><Droplets size={16} className="text-blue-500" />{deviceValue(humidity)}</span>}<span className={styles.pill}><ShieldCheck size={16} className="text-cyan-600" />{showcase ? "Showcase home" : connected ? "Connected" : "Offline"}</span></div><div className="flex gap-2"><button className={styles.action} onClick={() => { setShowcase(!showcase); setSelected(null); setError(""); setNotice(""); }}>{showcase ? "My home" : "View showcase"}</button>{owner && <button className={styles.action} onClick={() => { setCreate(true); setError(""); }}><Plus size={16} className="mr-1 inline" />Create room</button>}</div></div>
    {showcase && <div className="rounded-xl border border-cyan-200 bg-cyan-50 px-4 py-3 text-sm text-cyan-900"><strong>Interactive showcase</strong> · Example rooms and values. Tile controls change this preview only. Creating a room saves a real room in your home.</div>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}{notice && !selected && <p role="status" className="text-sm text-cyan-700">{notice}</p>}
    <div className="flex flex-wrap items-center gap-2"><select aria-label="Choose room" className={styles.action} value={roomFilter} onChange={e => setRoomFilter(e.target.value)}><option value="all">All rooms</option>{names.map(room => <option key={room}>{room}</option>)}</select>{["all", "light", "switch", "climate", "camera", "sensor", "media_player", "cover"].map(domain => <button key={domain} aria-pressed={filter === domain} className={styles.action + (filter === domain ? " ring-1 ring-cyan-500" : "")} onClick={() => setFilter(domain)}>{domain === "all" ? "All devices" : domain.replace("_", " ")}</button>)}</div>
    <div className={styles.rooms}>{names.filter(room => roomFilter === "all" || roomFilter === room).map(room => {
      const metadata = rooms.find(row => row.name === room); const Icon = roomIcon(room, metadata?.kind);
      const rows = visible.filter(row => (row.room || "Unassigned") === room);
      const temp = source.find(row => row.room === room && row.attributes.device_class === "temperature"); const humid = source.find(row => row.room === room && row.attributes.device_class === "humidity");
      return <section key={room} className={styles.room}><header className={styles.roomHeading}><h3 className={styles.roomTitle}><Icon size={21} />{room}</h3><div className="flex gap-3 text-xs text-gray-500">{temp && <span><Thermometer size={13} className="mr-1 inline text-red-500" />{deviceValue(temp)}</span>}{humid && <span><Droplets size={13} className="mr-1 inline text-blue-500" />{deviceValue(humid)}</span>}</div></header><div className={styles.tiles}>{rows.map(row => { const Icon = deviceIcon(row); return <button key={row.id} className={styles.tile} onClick={() => open(row)} aria-label={row.name + ", " + deviceValue(row) + ". Open controls."}><span className={styles.icon + " " + (row.domain === "light" && row.state === "on" ? styles.on : row.domain === "media_player" ? styles.media : row.domain === "cover" ? styles.cover : row.domain === "sensor" ? styles.sensor : "")}><Icon size={24} /></span><span className="min-w-0 flex-1"><span className={styles.tileName}>{row.name}</span><span className={styles.tileValue}>{deviceValue(row)}</span>{row.domain === "light" && typeof row.attributes.brightness === "number" && <span className={styles.meter + " block"}><span className={styles.fill + " block"} style={{ width: row.state === "on" ? Math.round(row.attributes.brightness / 255 * 100) + "%" : "0%" }} /></span>}</span></button>; })}</div>{!rows.length && <div className={styles.empty}>{filter === "all" ? "This room is ready for devices. Assign a synced device from its control pop-up." : "No devices match this filter in this room."}</div>}</section>;
    })}</div>{!names.length && <div className={styles.empty}><DoorOpen className="mb-3" /><p className="font-medium">Create your first room</p><p className="mt-2">Rooms stay visible while you connect and organise devices. Use View showcase to try the controls.</p></div>}
    {create && <Modal title="Create a room" close={() => setCreate(false)}><form className="mt-5 space-y-4" onSubmit={async e => { e.preventDefault(); if (await mutate("/" + homeId + "/rooms", "POST", { name, kind })) { setName(""); setCreate(false); setShowcase(false); } }}><p className="text-sm text-gray-500">Saved to this home, even before your gateway is connected.</p><label className="block text-sm">Room name<input autoFocus required maxLength={128} className={styles.field} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Living room" /></label><label className="block text-sm">Room type<select className={styles.field} value={kind} onChange={e => setKind(e.target.value)}>{["living", "kitchen", "bedroom", "bathroom", "office", "garage", "garden", "energy", "other"].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>{error && <p role="alert" className="text-sm text-red-600">{error}</p>}<button className={styles.action} disabled={working || !name.trim()}>Create room</button></form></Modal>}
    {current && <Modal title={current.name} close={() => setSelected(null)}><p className="mt-2 text-sm text-gray-500">{current.room || "Unassigned"} · {showcase ? "Showcase · preview controls only" : current.observed_at ? "Updated " + new Date(current.observed_at).toLocaleString("en-ZA") : "Waiting for readings"}</p><p className="mt-7 text-center text-4xl font-light">{controlValue(current, level)}</p>
      {current.domain === "light" && typeof current.attributes.brightness === "number" && <label><span className="sr-only">{current.name} brightness</span><input className={styles.dimmer} type="range" min="0" max="100" value={level} disabled={disabled} aria-label="Brightness" style={{ background: "linear-gradient(to top, #ffa447 " + level + "%, #ffecd9 " + level + "%)" }} onChange={e => setLevel(Number(e.target.value))} /></label>}
      <div className="my-6 flex flex-wrap justify-center gap-3">{["light", "switch", "fan"].includes(current.domain) && <><button className={styles.action} disabled={disabled} onClick={() => void send(current.state === "on" ? "turn_off" : "turn_on")}><Power size={17} className="mr-2 inline" />{current.state === "on" ? "Turn off" : "Turn on"}</button>{current.domain === "light" && typeof current.attributes.brightness === "number" && <button className={styles.action} disabled={disabled} onClick={() => void send("turn_on", { brightness_pct: level })}>Set brightness</button>}</>}
      {current.domain === "cover" && <><button className={styles.action} disabled={disabled} onClick={() => void send("open_cover")}>Open</button><button className={styles.action} disabled={disabled} onClick={() => void send("close_cover")}>Close</button>{typeof current.attributes.current_position === "number" && <label className="w-full text-sm">Position<input aria-label="Blind position" type="range" min="0" max="100" className="mt-3 w-full accent-violet-500" value={level} onChange={e => setLevel(Number(e.target.value))} disabled={disabled} /><button className={styles.action + " mt-3"} disabled={disabled} onClick={() => void send("set_cover_position", { position: level })}>Set position</button></label>}</>}
      {current.domain === "scene" && <button className={styles.action} disabled={disabled} onClick={() => void send("turn_on")}>Activate scene</button>}
      {current.domain === "media_player" && (showcase ? <button className={styles.action} onClick={() => void send(current.state === "playing" ? "media_pause" : "media_play")}>{current.state === "playing" ? <Pause size={20} /> : <Play size={20} />}</button> : owner && <button className={styles.action} onClick={openMedia}><Speaker size={18} className="mr-2 inline" />Open Media controls</button>)}
      </div>{current.domain === "camera" && (camera && !showcase ? cameraPreview(current) : <p className="text-sm text-gray-500">Camera access needs a separate approved permission.</p>)}
      {!showcase && !connected && <p className="my-3 text-sm text-amber-700">The gateway is offline. Controls are disabled; these are stored readings.</p>}{!showcase && !control && <p className="my-3 text-sm text-gray-500">Read-only access. Device control requires the home owner's approval.</p>}
      {["sensor", "binary_sensor", "climate", "lock", "alarm_control_panel"].includes(current.domain) && <dl className="my-4 space-y-2 text-sm">{Object.entries(current.attributes).filter(([key]) => ["unit_of_measurement", "device_class", "temperature", "current_temperature", "humidity", "battery_level"].includes(key)).map(([key, value]) => <div key={key} className="flex justify-between gap-4"><dt className="text-gray-500">{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>}
      {!showcase && owner && rooms.length > 0 && <label className="mt-5 block text-sm">Move to room<select className={styles.field} value={rooms.find(room => room.name === current.room)?.id || ""} disabled={working} onChange={e => { if (e.target.value) void mutate("/" + homeId + "/rooms/" + e.target.value + "/devices/" + current.id, "PUT", {}); }}><option value="">Select room</option>{rooms.map(room => <option key={room.id} value={room.id}>{room.name}</option>)}</select></label>}
      {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}{notice && <p role="status" className="mt-4 text-sm text-cyan-700">{notice}</p>}
    </Modal>}
  </div>;
}

