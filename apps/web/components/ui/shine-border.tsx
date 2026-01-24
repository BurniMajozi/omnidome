"use client"

import { cn } from "@/lib/utils"

interface ShineBorderProps {
  children: React.ReactNode
  className?: string
  borderRadius?: number
  borderWidth?: number
  duration?: number
  color?: string | string[]
}

export function ShineBorder({
  children,
  className,
  borderRadius = 8,
  borderWidth = 1,
  duration = 14,
  color = ["#6366f1", "#8b5cf6", "#06b6d4"],
}: ShineBorderProps) {
  return (
    <div
      style={{
        "--border-radius": `${borderRadius}px`,
        "--border-width": `${borderWidth}px`,
        "--duration": `${duration}s`,
        "--mask-linear-gradient": `linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)`,
        "--background-radial-gradient": `radial-gradient(transparent, transparent, ${Array.isArray(color) ? color.join(",") : color}, transparent, transparent)`,
      } as React.CSSProperties}
      className={cn(
        "relative rounded-[--border-radius] p-[--border-width]",
        "before:absolute before:inset-0 before:rounded-[--border-radius]",
        "before:p-[--border-width] before:will-change-[background-position]",
        "before:content-[''] before:![-webkit-mask-composite:xor]",
        "before:[background-image:--background-radial-gradient]",
        "before:[background-size:300%_300%]",
        "before:[mask-composite:exclude]",
        "before:[mask:--mask-linear-gradient]",
        "motion-safe:before:animate-shine-border",
        className
      )}
    >
      {children}
    </div>
  )
}
