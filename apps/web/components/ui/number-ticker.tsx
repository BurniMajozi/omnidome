"use client"

import { useEffect, useRef, useState } from "react"
import { useInView, useMotionValue, useSpring } from "framer-motion"
import { cn } from "@/lib/utils"

interface NumberTickerProps {
  value: number
  direction?: "up" | "down"
  delay?: number
  className?: string
  decimalPlaces?: number
  suffix?: string
  prefix?: string
  trigger?: boolean
}

export function NumberTicker({
  value,
  direction = "up",
  delay = 0,
  className,
  decimalPlaces = 0,
  suffix = "",
  prefix = "",
  trigger,
}: NumberTickerProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const motionValue = useMotionValue(direction === "down" ? value : 0)
  const springValue = useSpring(motionValue, {
    damping: 60,
    stiffness: 100,
  })
  const isInView = useInView(ref, { once: trigger === undefined, margin: "0px" })
  const [displayValue, setDisplayValue] = useState(direction === "down" ? value : 0)

  // Reset and animate when trigger changes
  useEffect(() => {
    if (trigger !== undefined) {
      if (trigger) {
        motionValue.set(0)
        const timer = setTimeout(() => {
          motionValue.set(direction === "down" ? 0 : value)
        }, delay * 1000)
        return () => clearTimeout(timer)
      }
    }
  }, [trigger, motionValue, delay, value, direction])

  // Original in-view behavior when no trigger is provided
  useEffect(() => {
    if (trigger === undefined && isInView) {
      const timer = setTimeout(() => {
        motionValue.set(direction === "down" ? 0 : value)
      }, delay * 1000)
      return () => clearTimeout(timer)
    }
  }, [motionValue, isInView, delay, value, direction, trigger])

  useEffect(() => {
    const unsubscribe = springValue.on("change", (latest) => {
      setDisplayValue(latest)
    })
    return () => unsubscribe()
  }, [springValue])

  return (
    <span
      ref={ref}
      className={cn(
        "inline-block tabular-nums tracking-tight",
        className
      )}
    >
      {prefix}
      {Intl.NumberFormat("en-US", {
        minimumFractionDigits: decimalPlaces,
        maximumFractionDigits: decimalPlaces,
      }).format(displayValue)}
      {suffix}
    </span>
  )
}
