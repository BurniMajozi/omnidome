import { NextRequest, NextResponse } from "next/server"

export interface VoipHardwareDevice {
  id: string
  brand: "Yealink" | "Grandstream" | "Cisco" | "Polycom" | "Fanvil" | "AudioCodes ATA"
  model: string
  mac_address: string
  assigned_extension: string
  agent_name: string
  ip_address: string
  firmware_version: string
  provisioning_url: string
  sip_transport: "TLS" | "UDP" | "TCP" | "WSS (WebRTC)"
  status: "REGISTERED" | "IN_CALL" | "RINGING" | "UNREACHABLE" | "PROVISIONING_PENDING"
  codec_priority: string[]
  last_registered_at: string
}

let hardwareDevices: VoipHardwareDevice[] = [
  {
    id: "hw-001",
    brand: "Yealink",
    model: "SIP-T46U Gigabit Executive IP Phone",
    mac_address: "80:5E:C0:11:A2:40",
    assigned_extension: "101",
    agent_name: "Sarah Mbeki",
    ip_address: "192.168.10.141",
    firmware_version: "66.86.0.40 (Latest)",
    provisioning_url: "https://prov.omnidome.internal/yealink/805ec011a240.cfg",
    sip_transport: "TLS",
    status: "REGISTERED",
    codec_priority: ["G.722 (HD Voice)", "Opus", "G.711a (PCMA)"],
    last_registered_at: "2 mins ago",
  },
  {
    id: "hw-002",
    brand: "Grandstream",
    model: "GRP2615 10-Line Carrier-Grade IP Phone",
    mac_address: "00:0B:82:F1:44:8E",
    assigned_extension: "104",
    agent_name: "Johan Pretorius (NOC Lead)",
    ip_address: "192.168.10.155",
    firmware_version: "1.0.7.33",
    provisioning_url: "https://prov.omnidome.internal/grandstream/cfg000b82f1448e.xml",
    sip_transport: "TLS",
    status: "IN_CALL",
    codec_priority: ["G.722", "PCMA", "iLBC"],
    last_registered_at: "1 min ago",
  },
  {
    id: "hw-003",
    brand: "Cisco",
    model: "IP Phone 8841 Multiplatform Firmware",
    mac_address: "F8:66:F2:88:19:0C",
    assigned_extension: "103",
    agent_name: "Rethabile Sekhoto (Finance)",
    ip_address: "192.168.10.170",
    firmware_version: "11.3.7MPP",
    provisioning_url: "https://prov.omnidome.internal/cisco/F866F288190C.xml",
    sip_transport: "TLS",
    status: "REGISTERED",
    codec_priority: ["G.722", "Opus", "PCMU"],
    last_registered_at: "4 mins ago",
  },
  {
    id: "hw-004",
    brand: "AudioCodes ATA",
    model: "MediaPack MP-118 8-Port FXS Gateway",
    mac_address: "00:90:8F:22:90:1B",
    assigned_extension: "110-117 (Analog Splicing Van Link)",
    agent_name: "Field Operations Radio / FXS",
    ip_address: "192.168.10.200",
    firmware_version: "6.60A.332",
    provisioning_url: "https://prov.omnidome.internal/audiocodes/ini/mp118.ini",
    sip_transport: "UDP",
    status: "REGISTERED",
    codec_priority: ["PCMA", "G.729"],
    last_registered_at: "12 mins ago",
  },
]

export async function GET() {
  const onlineCount = hardwareDevices.filter((d) => d.status === "REGISTERED" || d.status === "IN_CALL").length
  return NextResponse.json({
    devices: hardwareDevices,
    stats: {
      total_hardware_units: hardwareDevices.length,
      online_active: onlineCount,
      unreachable_faults: hardwareDevices.filter((d) => d.status === "UNREACHABLE").length,
      auto_provisioning_server: "tftp://prov.omnidome.internal / https://prov.omnidome.internal",
      supported_brands: ["Yealink", "Grandstream", "Cisco MPP", "Polycom VVX", "Fanvil", "AudioCodes"],
    },
  })
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const { brand, model, mac_address, assigned_extension, agent_name, ip_address, sip_transport } = body

    if (!brand || !model || !mac_address || !assigned_extension) {
      return NextResponse.json({ error: "Missing required fields (brand, model, MAC, extension)" }, { status: 400 })
    }

    const cleanMac = mac_address.replace(/[:-]/g, "").toLowerCase()
    const autoCfgUrl = `https://prov.omnidome.internal/${brand.toLowerCase()}/${cleanMac}.cfg`

    const newDevice: VoipHardwareDevice = {
      id: `hw-${Date.now()}`,
      brand,
      model,
      mac_address: mac_address.toUpperCase(),
      assigned_extension,
      agent_name: agent_name || `Agent ${assigned_extension}`,
      ip_address: ip_address || "192.168.10.1" + Math.floor(Math.random() * 80 + 20),
      firmware_version: "Auto-Provisioning Assigned",
      provisioning_url: autoCfgUrl,
      sip_transport: sip_transport || "TLS",
      status: "REGISTERED",
      codec_priority: ["G.722 (HD Voice)", "Opus", "PCMA"],
      last_registered_at: "Just now",
    }

    hardwareDevices.unshift(newDevice)
    return NextResponse.json({ success: true, device: newDevice })
  } catch (err: any) {
    return NextResponse.json({ error: err.message || "Failed to add hardware" }, { status: 500 })
  }
}

export async function DELETE(req: NextRequest) {
  const url = new URL(req.url)
  const id = url.searchParams.get("id")
  if (!id) return NextResponse.json({ error: "Missing device id" }, { status: 400 })

  hardwareDevices = hardwareDevices.filter((d) => d.id !== id)
  return NextResponse.json({ success: true, remaining: hardwareDevices.length })
}
