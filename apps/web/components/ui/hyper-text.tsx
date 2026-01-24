"use client"

import { useEffect, useRef, useState } from "react"
import { AnimatePresence, motion, MotionProps } from "framer-motion"
import { cn } from "@/lib/utils"

type CharacterSet = string[] | readonly string[]

interface HyperTextProps extends MotionProps {
  children: string
  className?: string
  duration?: number
  delay?: number
  as?: React.ElementType
  startOnView?: boolean
  animateOnHover?: boolean
  characterSet?: CharacterSet
}

const DEFAULT_CHARACTER_SET = Object.freeze(
  "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789".split("")
) as readonly string[]

const getRandomChar = (set: CharacterSet) =>
  set[Math.floor(Math.random() * set.length)]

export function HyperText({
  children,
  className,
  duration = 800,
  delay = 0,
  as: Component = "div",
  startOnView = false,
  animateOnHover = true,
  characterSet = DEFAULT_CHARACTER_SET,
  ...props
}: HyperTextProps) {
  const [displayText, setDisplayText] = useState<string[]>(() =>
    children.split("")
  )
  const [isAnimating, setIsAnimating] = useState(false)
  const iterationCount = useRef(0)
  const elementRef = useRef<HTMLDivElement>(null)

  const handleAnimationTrigger = () => {
    if (isAnimating) return
    iterationCount.current = 0
    setIsAnimating(true)
  }

  useEffect(() => {
    if (!isAnimating) return

    const intervalDuration = duration / (children.length * 10)
    const maxIterations = children.length

    const interval = setInterval(() => {
      if (iterationCount.current < maxIterations) {
        setDisplayText((prev) =>
          prev.map((char, index) => {
            if (char === " ") return " "
            if (index <= iterationCount.current) {
              return children[index]
            }
            return getRandomChar(characterSet)
          })
        )
        iterationCount.current += 0.5
      } else {
        setIsAnimating(false)
        clearInterval(interval)
      }
    }, intervalDuration)

    return () => clearInterval(interval)
  }, [isAnimating, children, duration, characterSet])

  useEffect(() => {
    setDisplayText(children.split(""))
  }, [children])

  useEffect(() => {
    if (!startOnView) {
      const startTimeout = setTimeout(handleAnimationTrigger, delay)
      return () => clearTimeout(startTimeout)
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setTimeout(handleAnimationTrigger, delay)
          observer.disconnect()
        }
      },
      { threshold: 0.1, rootMargin: "-30% 0px -30% 0px" }
    )

    if (elementRef.current) {
      observer.observe(elementRef.current)
    }

    return () => observer.disconnect()
  }, [delay, startOnView])

  return (
    <Component
      ref={elementRef}
      className={cn("overflow-hidden", className)}
      onMouseEnter={animateOnHover ? handleAnimationTrigger : undefined}
      {...props}
    >
      <AnimatePresence mode="popLayout">
        {displayText.map((char, index) => (
          <motion.span
            key={`${index}-${char}`}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            transition={{
              duration: 0.1,
              delay: index * 0.015,
            }}
            className="inline-block"
          >
            {char === " " ? "\u00A0" : char}
          </motion.span>
        ))}
      </AnimatePresence>
    </Component>
  )
}
