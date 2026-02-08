"use client"

import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"
import { motion } from "framer-motion"

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

function NumberTicker({ value }: { value: number }) {
  return (
    <motion.span
      key={value}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="text-xs font-bold text-white tabular-nums"
    >
      {value.toFixed(0)}%
    </motion.span>
  )
}

export function GrowthGraphDemo({ className }: { className?: string }) {
  const [animated, setAnimated] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const maxValue = Math.max(...data.map((d) => d.value))
  const minValue = Math.min(...data.map((d) => d.value))
  
  // Chart dimensions
  const chartWidth = 100 // percentage
  const chartHeight = 100 // percentage
  const padding = { top: 10, right: 5, bottom: 5, left: 5 }
  
  // Calculate points for the line
  const points = data.map((point, index) => {
    const x = padding.left + (index / (data.length - 1)) * (chartWidth - padding.left - padding.right)
    const y = padding.top + ((maxValue - point.value) / (maxValue - minValue + 10)) * (chartHeight - padding.top - padding.bottom)
    return { x, y, value: point.value, label: point.label }
  })
  
  // Create SVG path
  const linePath = points
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')
  
  // Create area path (for gradient fill)
  const areaPath = `${linePath} L ${points[points.length - 1].x} ${chartHeight} L ${points[0].x} ${chartHeight} Z`

  useEffect(() => {
    const timer = setTimeout(() => setAnimated(true), 100)
    return () => clearTimeout(timer)
  }, [])

  // Animate the ticker along the line
  useEffect(() => {
    if (!animated) return
    
    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % points.length)
    }, 1500)
    
    return () => clearInterval(interval)
  }, [animated, points.length])

  const currentPoint = points[currentIndex]

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

      <div className="relative flex-1 min-h-[140px]">
        <svg
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
        >
          <defs>
            <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#818cf8" />
              <stop offset="50%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#10b981" />
            </linearGradient>
            <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" stopOpacity="0.3" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="2" result="coloredBlur" />
              <feMerge>
                <feMergeNode in="coloredBlur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          
          {/* Area fill */}
          <motion.path
            d={areaPath}
            fill="url(#areaGradient)"
            initial={{ opacity: 0 }}
            animate={{ opacity: animated ? 1 : 0 }}
            transition={{ duration: 1, delay: 0.5 }}
          />
          
          {/* Line */}
          <motion.path
            d={linePath}
            fill="none"
            stroke="url(#lineGradient)"
            strokeWidth="0.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            filter="url(#glow)"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: animated ? 1 : 0, opacity: animated ? 1 : 0 }}
            transition={{ duration: 2, ease: "easeOut" }}
          />
          
          {/* Data points */}
          {points.map((point, index) => (
            <motion.circle
              key={index}
              cx={point.x}
              cy={point.y}
              r="1.2"
              fill={index === currentIndex ? "#10b981" : "#6366f1"}
              stroke={index === currentIndex ? "#10b981" : "#818cf8"}
              strokeWidth="0.5"
              initial={{ opacity: 0, scale: 0 }}
              animate={{ 
                opacity: animated ? 1 : 0, 
                scale: animated ? (index === currentIndex ? 1.5 : 1) : 0 
              }}
              transition={{ 
                duration: 0.3, 
                delay: animated ? index * 0.1 : 0 
              }}
            />
          ))}
        </svg>
        
        {/* Animated ticker following the line */}
        {animated && (
          <motion.div
            className="absolute flex flex-col items-center pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{
              opacity: 1,
              left: `${currentPoint.x}%`,
              top: `${currentPoint.y - 15}%`,
            }}
            transition={{
              duration: 0.5,
              ease: "easeInOut"
            }}
            style={{
              transform: 'translate(-50%, -100%)'
            }}
          >
            <motion.div
              className="px-2 py-1 rounded-md bg-emerald-500/20 border border-emerald-500/50 backdrop-blur-sm"
              initial={{ scale: 0.8 }}
              animate={{ scale: [0.9, 1.1, 1] }}
              transition={{ duration: 0.3 }}
            >
              <NumberTicker value={currentPoint.value} />
            </motion.div>
            <motion.div
              className="w-0.5 h-2 bg-gradient-to-b from-emerald-500 to-transparent"
              initial={{ scaleY: 0 }}
              animate={{ scaleY: 1 }}
              transition={{ duration: 0.2 }}
            />
          </motion.div>
        )}
        
        {/* Glowing pulse at current point */}
        {animated && (
          <motion.div
            className="absolute w-4 h-4 rounded-full bg-emerald-500/30 pointer-events-none"
            animate={{
              left: `${currentPoint.x}%`,
              top: `${currentPoint.y}%`,
              scale: [1, 2, 1],
              opacity: [0.5, 0, 0.5],
            }}
            transition={{
              left: { duration: 0.5, ease: "easeInOut" },
              top: { duration: 0.5, ease: "easeInOut" },
              scale: { duration: 1.5, repeat: Infinity },
              opacity: { duration: 1.5, repeat: Infinity },
            }}
            style={{
              transform: 'translate(-50%, -50%)'
            }}
          />
        )}
      </div>

      {/* X-axis labels */}
      <div className="flex justify-between mt-2 px-1">
        {data.filter((point, i) => i % 3 === 0 || i === data.length - 1).map((point, index) => (
          <span key={index} className="text-[10px] text-slate-500">{point.label}</span>
        ))}
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
