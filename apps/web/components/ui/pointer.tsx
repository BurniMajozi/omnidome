"use client"

import { cn } from "@/lib/utils"
import { AnimatePresence, motion, useMotionValue } from "framer-motion"
import React, { useEffect, useState } from "react"

interface PointerProps {
  children?: React.ReactNode
  className?: string
  name?: string
}

export function Pointer({ children, className, name }: PointerProps) {
  const x = useMotionValue(0)
  const y = useMotionValue(0)
  const [isVisible, setIsVisible] = useState(false)
  const [rect, setRect] = useState<DOMRect | null>(null)
  const ref = React.useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) {
      setRect(ref.current.getBoundingClientRect())
    }
  }, [])

  useEffect(() => {
    const updateRect = () => {
      if (ref.current) {
        setRect(ref.current.getBoundingClientRect())
      }
    }
    window.addEventListener("resize", updateRect)
    window.addEventListener("scroll", updateRect)
    return () => {
      window.removeEventListener("resize", updateRect)
      window.removeEventListener("scroll", updateRect)
    }
  }, [])

  const handleMouseMove = (e: React.MouseEvent) => {
    if (rect) {
      x.set(e.clientX - rect.left)
      y.set(e.clientY - rect.top)
    }
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      className={cn("absolute inset-0", isVisible && "cursor-none")}
    >
      <AnimatePresence>
        {isVisible && (
          <motion.div
            className={cn(
              "pointer-events-none absolute z-50",
              className
            )}
            style={{
              x,
              y,
              translateX: "-50%",
              translateY: "-50%",
            }}
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.5 }}
            transition={{ duration: 0.15 }}
          >
            {children || (
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className={cn("fill-primary", className)}
              >
                <path d="M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87c.48 0 .72-.58.38-.92L6.35 2.79a.5.5 0 0 0-.85.42Z" />
              </svg>
            )}
            {name && (
              <motion.div
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 5 }}
                className="ml-4 mt-1 whitespace-nowrap rounded-full bg-primary px-2 py-0.5 text-xs text-primary-foreground"
              >
                {name}
              </motion.div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Emoji pointer with animation
export function EmojiPointer({ emoji = "👆", className }: { emoji?: string; className?: string }) {
  return (
    <Pointer className={className}>
      <motion.div
        animate={{
          scale: [1, 1.2, 1],
          rotate: [0, 5, -5, 0],
        }}
        transition={{
          duration: 1,
          repeat: Infinity,
          ease: "easeInOut",
        }}
        className="text-2xl drop-shadow-lg"
      >
        {emoji}
      </motion.div>
    </Pointer>
  )
}

// Animated heart pointer
export function HeartPointer({ className }: { className?: string }) {
  return (
    <Pointer className={className}>
      <motion.div
        animate={{
          scale: [0.8, 1, 0.8],
        }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      >
        <svg
          width="32"
          height="32"
          viewBox="0 0 24 24"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="text-pink-500 drop-shadow-[0_0_8px_rgba(236,72,153,0.8)]"
        >
          <motion.path
            d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
            fill="currentColor"
            animate={{ scale: [1, 1.1, 1] }}
            transition={{
              duration: 0.8,
              repeat: Infinity,
              ease: "easeInOut",
            }}
          />
        </svg>
      </motion.div>
    </Pointer>
  )
}

export function PointerHighlight({
  children,
  pointerColor = "fill-indigo-500",
  pointerContent,
}: {
  children: React.ReactNode
  pointerColor?: string
  pointerContent?: React.ReactNode
}) {
  return (
    <div className="group relative">
      {children}
      <Pointer className={pointerColor}>{pointerContent}</Pointer>
    </div>
  )
}
