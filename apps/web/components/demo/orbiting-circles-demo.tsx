"use client"

import { cn } from "@/lib/utils"
import { OrbitingCircles } from "@/components/ui/orbiting-circles"
import { Wifi, Users, Receipt, Phone, Megaphone, DollarSign, Headset, Globe } from "lucide-react"

export function OrbitingCirclesDemo({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative flex h-full w-full flex-col items-center justify-center overflow-hidden",
        className
      )}
    >
      <span className="pointer-events-none whitespace-pre-wrap bg-gradient-to-b from-white to-slate-400 bg-clip-text text-center text-4xl font-bold leading-none text-transparent">
        Hub
      </span>

      {/* Inner Circles */}
      <OrbitingCircles
        className="size-[40px] border-none bg-transparent"
        duration={20}
        delay={20}
        radius={60}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Users className="size-5 text-indigo-400" />
        </div>
      </OrbitingCircles>
      <OrbitingCircles
        className="size-[40px] border-none bg-transparent"
        duration={20}
        delay={10}
        radius={60}
      >
        <div className="flex size-10 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Receipt className="size-5 text-green-400" />
        </div>
      </OrbitingCircles>

      {/* Outer Circles (Reverse) */}
      <OrbitingCircles
        className="size-[50px] border-none bg-transparent"
        radius={120}
        duration={20}
        reverse
      >
        <div className="flex size-12 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Wifi className="size-6 text-cyan-400" />
        </div>
      </OrbitingCircles>
      <OrbitingCircles
        className="size-[50px] border-none bg-transparent"
        radius={120}
        duration={20}
        delay={20}
        reverse
      >
        <div className="flex size-12 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Phone className="size-6 text-blue-400" />
        </div>
      </OrbitingCircles>
    </div>
  )
}

export function OrbitingCirclesDemo2({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative flex h-full w-full flex-col items-center justify-center overflow-hidden",
        className
      )}
    >
      <span className="pointer-events-none whitespace-pre-wrap bg-gradient-to-b from-indigo-400 to-cyan-400 bg-clip-text text-center text-3xl font-bold leading-none text-transparent">
        Connect
      </span>

      {/* Inner Circles */}
      <OrbitingCircles
        className="size-[36px] border-none bg-transparent"
        duration={15}
        delay={5}
        radius={50}
      >
        <div className="flex size-9 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Headset className="size-4 text-purple-400" />
        </div>
      </OrbitingCircles>
      <OrbitingCircles
        className="size-[36px] border-none bg-transparent"
        duration={15}
        delay={15}
        radius={50}
      >
        <div className="flex size-9 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Megaphone className="size-4 text-rose-400" />
        </div>
      </OrbitingCircles>

      {/* Outer Circles */}
      <OrbitingCircles
        className="size-[44px] border-none bg-transparent"
        radius={100}
        duration={25}
      >
        <div className="flex size-11 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <Globe className="size-5 text-emerald-400" />
        </div>
      </OrbitingCircles>
      <OrbitingCircles
        className="size-[44px] border-none bg-transparent"
        radius={100}
        duration={25}
        delay={12}
      >
        <div className="flex size-11 items-center justify-center rounded-full bg-slate-800 border border-slate-700">
          <DollarSign className="size-5 text-amber-400" />
        </div>
      </OrbitingCircles>
    </div>
  )
}
