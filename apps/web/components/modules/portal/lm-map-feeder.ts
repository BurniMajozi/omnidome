/**
 * LM (Line & Marker) Fiber Route & Geographic Feasibility Data
 *
 * Supports GIS / KML / GeoJSON fiber route structures for South African FTTH/B operators:
 * - Openserve
 * - Vumatel
 * - Frogfoot
 * - Octotel
 * - MetroFibre
 *
 * Each zone defines geographic polygon markers, trench lines, OLT status,
 * and location-dependent product catalogs (speeds, pricing, installation times).
 */

export interface FiberProduct {
  id: string
  name: string
  speedDown: number // Mbps
  speedUp: number   // Mbps
  priceZar: number  // Monthly ZAR
  promoPriceZar?: number
  operator: "Vumatel" | "Openserve" | "Frogfoot" | "Octotel" | "MetroFibre"
  features: string[]
  freeInstall: boolean
  freeRouter: boolean
  slaDays: number
  recommended?: boolean
}

export interface LmZoneMarker {
  id: string
  name: string
  city: string
  province: string
  coverageStatus: "live" | "build" | "planned"
  operator: "Vumatel" | "Openserve" | "Frogfoot" | "Octotel" | "MetroFibre"
  coordinates: [number, number] // [lat, lng]
  trenchLines: Array<[number, number][]> // LM polyline vectors
  oltId: string
  splitterCapacity: string
  averageLatencyMs: number
  availableProducts: FiberProduct[]
}

export const LM_FIBER_ZONES: LmZoneMarker[] = [
  {
    id: "zone-cpt-cbd",
    name: "Cape Town CBD & Atlantic Seaboard",
    city: "Cape Town",
    province: "Western Cape",
    coverageStatus: "live",
    operator: "Octotel",
    coordinates: [-33.9249, 18.4241],
    trenchLines: [
      [
        [-33.924, 18.421],
        [-33.928, 18.426],
        [-33.931, 18.432],
      ],
    ],
    oltId: "CPT-CBD-OLT-01",
    splitterCapacity: "92% available (1:32 GPON)",
    averageLatencyMs: 3.2,
    availableProducts: [
      {
        id: "octo-100",
        name: "Octotel Home Flex 100M",
        speedDown: 100,
        speedUp: 100,
        priceZar: 599,
        promoPriceZar: 499,
        operator: "Octotel",
        features: ["Uncapped & Unshaped", "Zero Throttling", "Free Wi-Fi 6 Router"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
      },
      {
        id: "octo-400",
        name: "Octotel Lightning 400M",
        speedDown: 400,
        speedUp: 200,
        priceZar: 899,
        promoPriceZar: 799,
        operator: "Octotel",
        features: ["Ultra-low latency to CPT NAP", "4K Ultra-HD streaming", "Priority QoS"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
        recommended: true,
      },
      {
        id: "octo-1000",
        name: "Octotel Gigabit Pro 1000M",
        speedDown: 1000,
        speedUp: 500,
        priceZar: 1299,
        operator: "Octotel",
        features: ["Symmetric 1Gbps burst", "Dual-band Mesh Ready", "24/7 VIP Support"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 1,
      },
    ],
  },
  {
    id: "zone-jhb-sandton",
    name: "Sandton Central & Morningside",
    city: "Johannesburg",
    province: "Gauteng",
    coverageStatus: "live",
    operator: "Vumatel",
    coordinates: [-26.1076, 28.0567],
    trenchLines: [
      [
        [-26.105, 28.053],
        [-26.109, 28.059],
        [-26.113, 28.064],
      ],
    ],
    oltId: "JHB-SND-OLT-04",
    splitterCapacity: "88% available (1:64 XGS-PON)",
    averageLatencyMs: 4.1,
    availableProducts: [
      {
        id: "vuma-200",
        name: "Vuma Fibre Essential 200M",
        speedDown: 200,
        speedUp: 200,
        priceZar: 799,
        promoPriceZar: 699,
        operator: "Vumatel",
        features: ["Fully Uncapped", "Symmetric Speed", "UPS Backup Pack Included"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 3,
      },
      {
        id: "vuma-500",
        name: "Vuma Ultra Gamer 500M",
        speedDown: 500,
        speedUp: 250,
        priceZar: 1099,
        operator: "Vumatel",
        features: ["Optimized route to JINX", "Sub-5ms gaming ping", "Free Installation"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
        recommended: true,
      },
      {
        id: "vuma-1000",
        name: "Vuma Direct Gigabit 1000M",
        speedDown: 1000,
        speedUp: 500,
        priceZar: 1499,
        operator: "Vumatel",
        features: ["Dedicated fiber core", "Static IP Available", "99.9% Uptime Guarantee"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 1,
      },
    ],
  },
  {
    id: "zone-dbn-umhlanga",
    name: "Umhlanga Ridgeside & Gateway",
    city: "Durban",
    province: "KwaZulu-Natal",
    coverageStatus: "live",
    operator: "Frogfoot",
    coordinates: [-29.7297, 31.0667],
    trenchLines: [
      [
        [-29.726, 31.062],
        [-29.731, 31.068],
        [-29.735, 31.072],
      ],
    ],
    oltId: "DBN-UMH-OLT-02",
    splitterCapacity: "94% available (1:32 GPON)",
    averageLatencyMs: 5.6,
    availableProducts: [
      {
        id: "frog-100",
        name: "Frogfoot Air Stream 100M",
        speedDown: 100,
        speedUp: 50,
        priceZar: 649,
        operator: "Frogfoot",
        features: ["Uncapped Daytime & Night", "Free ONT Activation", "Voice-ready SIP"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 3,
      },
      {
        id: "frog-500",
        name: "Frogfoot Turbo Stream 500M",
        speedDown: 500,
        speedUp: 250,
        priceZar: 999,
        promoPriceZar: 899,
        operator: "Frogfoot",
        features: ["Durban Local Peer Cache", "Free Mesh Wi-Fi Extender", "Zero Contract Lock"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
        recommended: true,
      },
      {
        id: "frog-1000",
        name: "Frogfoot Enterprise Gig 1000M",
        speedDown: 1000,
        speedUp: 500,
        priceZar: 1349,
        operator: "Frogfoot",
        features: ["Enterprise ONT Unit", "Direct Durban Breakout", "24/7 NOC Monitoring"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 1,
      },
    ],
  },
  {
    id: "zone-pta-centurion",
    name: "Centurion & Midstream Estate",
    city: "Pretoria",
    province: "Gauteng",
    coverageStatus: "live",
    operator: "Openserve",
    coordinates: [-25.8603, 28.1894],
    trenchLines: [
      [
        [-25.856, 28.184],
        [-25.862, 28.191],
        [-25.867, 28.198],
      ],
    ],
    oltId: "PTA-CEN-OLT-03",
    splitterCapacity: "85% available (1:64 GPON)",
    averageLatencyMs: 4.8,
    availableProducts: [
      {
        id: "open-100",
        name: "Openserve WebConnect 100M",
        speedDown: 100,
        speedUp: 50,
        priceZar: 629,
        operator: "Openserve",
        features: ["Pure Uncapped", "Openserve Optical Network", "Includes Free Wi-Fi 6 Box"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 3,
      },
      {
        id: "open-250",
        name: "Openserve Fibre Boost 250M",
        speedDown: 250,
        speedUp: 125,
        priceZar: 849,
        promoPriceZar: 749,
        operator: "Openserve",
        features: ["Sub-6ms Gauteng loop", "Free standard installation", "Work-from-home SLA"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
        recommended: true,
      },
      {
        id: "open-500",
        name: "Openserve Prime Gig 500M",
        speedDown: 500,
        speedUp: 250,
        priceZar: 1049,
        operator: "Openserve",
        features: ["Top-tier optical port", "Static IP Add-on", "Priority dispatch"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 1,
      },
    ],
  },
  {
    id: "zone-cpt-bellville",
    name: "Bellville & Northern Suburbs",
    city: "Cape Town",
    province: "Western Cape",
    coverageStatus: "live",
    operator: "Openserve",
    coordinates: [-33.9036, 18.6384],
    trenchLines: [
      [
        [-33.901, 18.634],
        [-33.906, 18.641],
      ],
    ],
    oltId: "CPT-BEL-OLT-02",
    splitterCapacity: "96% available (1:32 GPON)",
    averageLatencyMs: 3.5,
    availableProducts: [
      {
        id: "bel-open-100",
        name: "Openserve Northern Sprint 100M",
        speedDown: 100,
        speedUp: 50,
        priceZar: 589,
        operator: "Openserve",
        features: ["True Uncapped", "Fast Bellville Hub connection", "Free Wi-Fi 6 Router"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
      },
      {
        id: "bel-open-300",
        name: "Openserve Northern Turbo 300M",
        speedDown: 300,
        speedUp: 150,
        priceZar: 829,
        promoPriceZar: 729,
        operator: "Openserve",
        features: ["Family streaming & gaming", "24/7 Western Cape Support", "Free ONT Setup"],
        freeInstall: true,
        freeRouter: true,
        slaDays: 2,
        recommended: true,
      },
    ],
  },
]

/**
 * Searches for an LM zone by freeform address or city query
 */
export function lookupLmZone(query: string): LmZoneMarker {
  const q = query.toLowerCase().trim()
  if (!q) return LM_FIBER_ZONES[0]

  const matched = LM_FIBER_ZONES.find(
    (z) =>
      z.name.toLowerCase().includes(q) ||
      z.city.toLowerCase().includes(q) ||
      z.province.toLowerCase().includes(q) ||
      z.operator.toLowerCase().includes(q)
  )

  return matched || LM_FIBER_ZONES[0]
}
