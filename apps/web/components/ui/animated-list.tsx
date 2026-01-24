"use client"

import { cn } from "@/lib/utils"
import { AnimatePresence, motion } from "framer-motion"
import { ReactElement, useEffect, useMemo, useState } from "react"

export interface AnimatedListProps {
  className?: string
  children: React.ReactNode
  delay?: number
}

export const AnimatedList = ({
  className,
  children,
  delay = 1000,
}: AnimatedListProps) => {
  const [index, setIndex] = useState(0)
  const childrenArray = useMemo(
    () => React.Children.toArray(children),
    [children]
  )

  useEffect(() => {
    const interval = setInterval(() => {
      setIndex((prevIndex) => (prevIndex + 1) % childrenArray.length)
    }, delay)

    return () => clearInterval(interval)
  }, [childrenArray.length, delay])

  const itemsToShow = useMemo(() => {
    const result = []
    for (let i = 0; i < Math.min(5, childrenArray.length); i++) {
      const idx = (index - i + childrenArray.length) % childrenArray.length
      result.push(childrenArray[idx])
    }
    return result.reverse()
  }, [index, childrenArray])

  return (
    <div className={cn("flex flex-col items-center gap-4", className)}>
      <AnimatePresence>
        {itemsToShow.map((item, i) => (
          <AnimatedListItem key={(item as ReactElement).key || i}>
            {item}
          </AnimatedListItem>
        ))}
      </AnimatePresence>
    </div>
  )
}

export function AnimatedListItem({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ scale: 0, opacity: 0 }}
      animate={{ scale: 1, opacity: 1, originY: 0 }}
      exit={{ scale: 0, opacity: 0 }}
      transition={{ type: "spring" as const, stiffness: 350, damping: 40 }}
      layout
      className="mx-auto w-full"
    >
      {children}
    </motion.div>
  )
}

import React from "react"
