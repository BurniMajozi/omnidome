"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { cn } from "@/lib/utils"

interface MorphingTextProps {
  texts: string[]
  className?: string
  morphTime?: number
  cooldownTime?: number
  onComplete?: () => void
}

export function MorphingText({
  texts,
  className,
  morphTime = 1,
  cooldownTime = 0.25,
  onComplete,
}: MorphingTextProps) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const [isComplete, setIsComplete] = useState(false)
  const text1Ref = useRef<HTMLSpanElement>(null)
  const text2Ref = useRef<HTMLSpanElement>(null)
  const morphRef = useRef(0)
  const cooldownRef = useRef(cooldownTime)
  const frameRef = useRef<number>()
  const lastTimeRef = useRef<number | null>(null)

  const setStyles = useCallback((fraction: number) => {
    const text1 = text1Ref.current
    const text2 = text2Ref.current
    if (!text1 || !text2) return

    text2.style.filter = `blur(${Math.min(8 / fraction - 8, 100)}px)`
    text2.style.opacity = `${Math.pow(fraction, 0.4) * 100}%`

    const inverseFraction = 1 - fraction
    text1.style.filter = `blur(${Math.min(8 / inverseFraction - 8, 100)}px)`
    text1.style.opacity = `${Math.pow(inverseFraction, 0.4) * 100}%`
  }, [])

  const doCooldown = useCallback(() => {
    morphRef.current = 0
    const text1 = text1Ref.current
    const text2 = text2Ref.current
    if (!text1 || !text2) return

    text2.style.filter = ""
    text2.style.opacity = "100%"
    text1.style.filter = ""
    text1.style.opacity = "0%"
  }, [])

  const doMorph = useCallback(() => {
    morphRef.current -= cooldownRef.current
    cooldownRef.current = 0

    let fraction = morphRef.current / morphTime

    if (fraction > 1) {
      cooldownRef.current = cooldownTime
      fraction = 1
    }

    setStyles(fraction)
  }, [morphTime, cooldownTime, setStyles])

  useEffect(() => {
    if (isComplete) return

    const animate = () => {
      const now = Date.now()
      const lastTime = lastTimeRef.current ?? now
      const dt = (now - lastTime) / 1000
      lastTimeRef.current = now

      cooldownRef.current -= dt

      if (cooldownRef.current <= 0) {
        doMorph()
        morphRef.current += dt
      } else {
        doCooldown()
      }

      // Check if morph is complete for current text
      if (morphRef.current >= morphTime) {
        morphRef.current = 0
        cooldownRef.current = cooldownTime

        const nextIndex = currentIndex + 1
        if (nextIndex >= texts.length) {
          setIsComplete(true)
          onComplete?.()
          return
        }
        setCurrentIndex(nextIndex)
      }

      frameRef.current = requestAnimationFrame(animate)
    }

    lastTimeRef.current = Date.now()
    frameRef.current = requestAnimationFrame(animate)

    return () => {
      if (frameRef.current) {
        cancelAnimationFrame(frameRef.current)
      }
    }
  }, [currentIndex, texts.length, morphTime, cooldownTime, doMorph, doCooldown, isComplete, onComplete])

  // Update text content when index changes
  useEffect(() => {
    const text1 = text1Ref.current
    const text2 = text2Ref.current
    if (!text1 || !text2) return

    text1.textContent = texts[currentIndex] || ""
    text2.textContent = texts[currentIndex + 1] || texts[currentIndex] || ""
  }, [currentIndex, texts])

  return (
    <div className={cn("relative inline-block min-w-[80px]", className)}>
      <span
        ref={text1Ref}
        className="absolute left-0 top-0"
        style={{ opacity: 1 }}
      />
      <span
        ref={text2Ref}
        className="relative"
        style={{ opacity: 0 }}
      />
    </div>
  )
}
