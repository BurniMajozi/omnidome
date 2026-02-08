"use client"

import { useState, useEffect, useRef } from "react"
import { useInView } from "framer-motion"
import { NumberTicker } from "@/components/ui/number-ticker"
import { MorphingText } from "@/components/ui/morphing-text"

const moduleNames = [
  "Chat",
  "Sales",
  "CRM",
  "Support",
  "Retain",
  "Network",
  "Calls",
  "Promo",
  "Comply",
  "Talent",
  "Billing",
  "Catalog",
  "Portal",
]

type AnimationPhase = "initial" | "morphing" | "continue"

export function AnimatedStats() {
  const containerRef = useRef<HTMLDivElement>(null)
  const isInView = useInView(containerRef, { once: false, margin: "-100px" })
  const [phase, setPhase] = useState<AnimationPhase>("initial")
  const [tickerKey, setTickerKey] = useState(0)

  // Reset animation when coming into view
  useEffect(() => {
    if (!isInView) return

    const startTimer = setTimeout(() => {
      setPhase("initial")
      setTickerKey(prev => prev + 1)
    }, 0)

    // After first ticker completes (~1.5s), start morphing
    const morphTimer = setTimeout(() => {
      setPhase("morphing")
    }, 1500)

    return () => {
      clearTimeout(startTimer)
      clearTimeout(morphTimer)
    }
  }, [isInView])

  const handleMorphComplete = () => {
    setPhase("continue")
    setTickerKey(prev => prev + 1)
    
    // After all animations complete, restart the loop
    setTimeout(() => {
      if (isInView) {
        setPhase("initial")
        setTickerKey(prev => prev + 1)
        
        setTimeout(() => {
          setPhase("morphing")
        }, 1500)
      }
    }, 5000) // Wait 5 seconds before looping
  }

  return (
    <div ref={containerRef} className="grid grid-cols-2 md:grid-cols-4 gap-12 max-w-5xl mx-auto border-t border-border pt-16">
      {/* Native Modules - with morphing text */}
      <div className="group">
        <div className="text-4xl lg:text-5xl font-black text-foreground mb-2 group-hover:text-indigo-500 transition-colors">
          {phase === "initial" && (
            <NumberTicker key={`modules-${tickerKey}`} value={13} trigger={isInView} />
          )}
          {phase === "morphing" && (
            <MorphingText
              texts={moduleNames}
              className="text-4xl lg:text-5xl font-black"
              morphTime={1}
              cooldownTime={0.3}
              onComplete={handleMorphComplete}
            />
          )}
          {phase === "continue" && (
            <NumberTicker key={`modules-done-${tickerKey}`} value={13} trigger={true} />
          )}
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-[3px] font-black">Native Modules</div>
      </div>

      {/* Churn Prediction */}
      <div className="group">
        <div className="text-4xl lg:text-5xl font-black text-foreground mb-2 group-hover:text-blue-500 transition-colors">
          {phase === "continue" ? (
            <NumberTicker key={`churn-${tickerKey}`} value={87} suffix="%" trigger={true} delay={0.2} />
          ) : (
            <NumberTicker key={`churn-init-${tickerKey}`} value={87} suffix="%" trigger={phase === "initial" && isInView} delay={0.1} />
          )}
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-[3px] font-black">Churn Prediction</div>
      </div>

      {/* Sales Velocity */}
      <div className="group">
        <div className="text-4xl lg:text-5xl font-black text-foreground mb-2 group-hover:text-cyan-500 transition-colors">
          {phase === "continue" ? (
            <NumberTicker key={`velocity-${tickerKey}`} value={2.4} decimalPlaces={1} suffix="x" trigger={true} delay={0.4} />
          ) : (
            <NumberTicker key={`velocity-init-${tickerKey}`} value={2.4} decimalPlaces={1} suffix="x" trigger={phase === "initial" && isInView} delay={0.2} />
          )}
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-[3px] font-black">Sales Velocity</div>
      </div>

      {/* SA Compliant */}
      <div className="group">
        <div className="text-4xl lg:text-5xl font-black text-foreground mb-2 group-hover:text-indigo-500 transition-colors">
          {phase === "continue" ? (
            <NumberTicker key={`compliant-${tickerKey}`} value={100} suffix="%" trigger={true} delay={0.6} />
          ) : (
            <NumberTicker key={`compliant-init-${tickerKey}`} value={100} suffix="%" trigger={phase === "initial" && isInView} delay={0.3} />
          )}
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-[3px] font-black">SA Compliant</div>
      </div>
    </div>
  )
}
