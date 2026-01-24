"use client"

import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"

interface DataPoint {
  label: string
  value: number
}

const data: DataPoint[] = [
  { label: "Jan", value: 35 },
  { label: "Feb", value: 42 },
  { label: "Mar", value: 38 },
  { label: "Apr", value: 55 },
  { label: "May", value: 62 },
  { label: "Jun", value: 58 },
  { label: "Jul", value: 72 },
  { label: "Aug", value: 85 },
  { label: "Sep", value: 78 },
  { label: "Oct", value: 92 },
  { label: "Nov", value: 88 },
  { label: "Dec", value: 100 },
]

export function GrowthGraphDemo({ className }: { className?: string }) {
  const [animated, setAnimated] = useState(false)
  const maxValue = Math.max(...data.map((d) => d.value))

  useEffect(() => {
    const timer = setTimeout(() => setAnimated(true), 100)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className={cn("flex h-full w-full flex-col p-6", className)}>
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h4 className="text-sm font-medium text-slate-400">Monthly Growth</h4>
          <p className="text-2xl font-bold text-white">+186%</p>
        </div>
        <div className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-1 text-xs font-medium text-emerald-400">
          <svg className="h-3 w-3" viewBox="0 0 12 12" fill="none">
            <path d="M6 2L10 7H2L6 2Z" fill="currentColor" />
          </svg>
          12.5%
        </div>
      </div>

      <div className="flex flex-1 items-end gap-2">
        {data.map((point, index) => {
          const height = (point.value / maxValue) * 100
          return (
            <div
              key={point.label}
              className="flex flex-1 flex-col items-center gap-2"
            >
              <div className="relative w-full flex-1 min-h-[120px]">
                <div
                  className={cn(
                    "absolute bottom-0 w-full rounded-t-md bg-gradient-to-t from-indigo-600 to-indigo-400 transition-all duration-1000 ease-out",
                    animated ? "opacity-100" : "opacity-0"
                  )}
                  style={{
                    height: animated ? `${height}%` : "0%",
                    transitionDelay: `${index * 50}ms`,
                  }}
                />
              </div>
              <span className="text-[10px] text-slate-500">{point.label}</span>
            </div>
          )
        })}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-slate-700/50 pt-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-indigo-500" />
            <span className="text-xs text-slate-400">Subscribers</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-emerald-500" />
            <span className="text-xs text-slate-400">Revenue</span>
          </div>
        </div>
        <span className="text-xs text-slate-500">2025</span>
      </div>
    </div>
  )
}
