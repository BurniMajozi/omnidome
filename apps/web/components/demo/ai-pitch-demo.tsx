"use client"

import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

interface PitchContent {
  company: string
  pitch: string
  details: string[]
  closing: string
}

const pitchData: PitchContent = {
  company: "Telkom Fibre",
  pitch: "OmniDome is transforming how ISPs manage their operations.",
  details: [
    "Our AI-powered platform revolutionizes ISP management by automating RICA compliance, streamlining billing cycles, and providing real-time network monitoring.",
    "With intelligent customer retention algorithms and unified communication tools, your team can focus on growth while we handle the complexity.",
    "Imagine having a virtual operations expert at your fingertips, instantly providing insights to reduce churn and increase subscriber satisfaction.",
  ],
  closing: "Join 50+ South African ISPs already scaling with OmniDome.",
}

function TypewriterText({ text, onComplete }: { text: string; onComplete?: () => void }) {
  const [displayedText, setDisplayedText] = useState("")
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (currentIndex < text.length) {
      const timer = setTimeout(() => {
        setDisplayedText(prev => prev + text[currentIndex])
        setCurrentIndex(prev => prev + 1)
      }, 15)
      return () => clearTimeout(timer)
    } else if (onComplete) {
      const timer = setTimeout(onComplete, 500)
      return () => clearTimeout(timer)
    }
  }, [currentIndex, text, onComplete])

  return <span>{displayedText}</span>
}

function Sparkle({ className, delay = 0 }: { className?: string; delay?: number }) {
  return (
    <motion.div
      className={cn("absolute text-yellow-400", className)}
      initial={{ opacity: 0, scale: 0 }}
      animate={{ 
        opacity: [0, 1, 1, 0],
        scale: [0, 1, 1, 0],
        rotate: [0, 15, -15, 0]
      }}
      transition={{
        duration: 2,
        delay,
        repeat: Infinity,
        repeatDelay: 3
      }}
    >
      ✦
    </motion.div>
  )
}

export function AIPitchDemo({ className }: { className?: string }) {
  const [phase, setPhase] = useState(0) // 0: company, 1: pitch, 2-4: details, 5: closing, 6: reset
  const [isGenerating, setIsGenerating] = useState(true)

  useEffect(() => {
    if (phase > 5) {
      // Reset after showing all content
      const resetTimer = setTimeout(() => {
        setPhase(0)
        setIsGenerating(true)
      }, 3000)
      return () => clearTimeout(resetTimer)
    }
  }, [phase])

  const handlePhaseComplete = () => {
    setPhase(prev => prev + 1)
    if (phase >= 5) {
      setIsGenerating(false)
    }
  }

  return (
    <div className={cn("relative flex h-full w-full items-center justify-center p-6", className)}>
      {/* Decorative sparkles */}
      <Sparkle className="top-8 left-12 text-lg" delay={0} />
      <Sparkle className="top-16 right-16 text-sm" delay={0.5} />
      <Sparkle className="bottom-24 left-20 text-base" delay={1} />
      <Sparkle className="top-12 right-8 text-xl" delay={1.5} />
      <Sparkle className="bottom-32 right-12 text-sm" delay={2} />
      
      {/* Main card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative w-full max-w-md bg-white dark:bg-slate-100 rounded-xl shadow-2xl overflow-hidden"
      >
        {/* Card header */}
        <div className="flex items-center gap-1.5 px-4 py-3 bg-slate-50 dark:bg-slate-200 border-b border-slate-200">
          <div className="w-3 h-3 rounded-full bg-red-400" />
          <div className="w-3 h-3 rounded-full bg-yellow-400" />
          <div className="w-3 h-3 rounded-full bg-green-400" />
        </div>
        
        {/* Card content */}
        <div className="p-5 space-y-4 min-h-[280px] max-h-[320px] overflow-hidden">
          {/* Company */}
          <div className="text-slate-800">
            <span className="font-semibold">Company: </span>
            {phase >= 0 && (
              <TypewriterText 
                text={pitchData.company} 
                onComplete={phase === 0 ? handlePhaseComplete : undefined}
              />
            )}
          </div>
          
          {/* Pitch intro */}
          {phase >= 1 && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-slate-700"
            >
              <span className="font-semibold text-slate-800">Pitch: </span>
              <TypewriterText 
                text={pitchData.pitch} 
                onComplete={phase === 1 ? handlePhaseComplete : undefined}
              />
            </motion.div>
          )}
          
          {/* Details */}
          {pitchData.details.map((detail, idx) => (
            phase >= idx + 2 && (
              <motion.p
                key={idx}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm text-slate-600 leading-relaxed"
              >
                <TypewriterText 
                  text={detail} 
                  onComplete={phase === idx + 2 ? handlePhaseComplete : undefined}
                />
              </motion.p>
            )
          ))}
          
          {/* Closing */}
          {phase >= 5 && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm text-indigo-600 font-medium"
            >
              <TypewriterText 
                text={pitchData.closing} 
                onComplete={phase === 5 ? handlePhaseComplete : undefined}
              />
            </motion.p>
          )}
        </div>
        
        {/* Generating indicator */}
        <div className="px-5 py-3 bg-slate-50 dark:bg-slate-200 border-t border-slate-200">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {isGenerating ? (
                <>
                  <motion.div
                    className="flex items-center gap-1"
                  >
                    <span className="text-sm text-slate-500">Generating the pitch</span>
                    <motion.span
                      animate={{ opacity: [1, 0, 1] }}
                      transition={{ duration: 1.5, repeat: Infinity }}
                      className="text-slate-500"
                    >
                      ...
                    </motion.span>
                  </motion.div>
                </>
              ) : (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="flex items-center gap-2 text-emerald-600"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="text-sm font-medium">Pitch complete!</span>
                </motion.div>
              )}
            </div>
            <motion.div
              animate={{ rotate: isGenerating ? 360 : 0 }}
              transition={{ duration: 2, repeat: isGenerating ? Infinity : 0, ease: "linear" }}
              className="text-indigo-500"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2L9.19 8.63L2 9.24L7.46 13.97L5.82 21L12 17.27L18.18 21L16.54 13.97L22 9.24L14.81 8.63L12 2Z" />
              </svg>
            </motion.div>
          </div>
        </div>
      </motion.div>
    </div>
  )
}
