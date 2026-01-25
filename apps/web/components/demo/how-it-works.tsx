"use client"

import { useRef, useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { cn } from "@/lib/utils"
import { AnimatedBeam } from "@/components/ui/animated-beam"
import { FileText, BarChart3, Check, ArrowRight } from "lucide-react"

// Animated Bar Graph Component
function AnimatedBarGraph({ className }: { className?: string }) {
  const bars = [
    { height: 30, delay: 0 },
    { height: 55, delay: 0.1 },
    { height: 45, delay: 0.2 },
    { height: 70, delay: 0.3 },
    { height: 40, delay: 0.4 },
    { height: 60, delay: 0.5 },
    { height: 85, delay: 0.6 },
  ]

  return (
    <div className={cn("flex items-end justify-center gap-1.5 h-20", className)}>
      {bars.map((bar, index) => (
        <motion.div
          key={index}
          className="w-4 bg-gradient-to-t from-indigo-500/30 to-indigo-400/60 rounded-t-sm"
          initial={{ height: 0 }}
          animate={{ 
            height: [0, bar.height, bar.height * 0.7, bar.height],
          }}
          transition={{
            duration: 2,
            delay: bar.delay,
            repeat: Infinity,
            repeatDelay: 1,
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  )
}

// Document Preview with scanning animation
function DocumentPreview({ className }: { className?: string }) {
  return (
    <div className={cn("relative bg-muted/30 rounded-lg p-4 border border-border/50", className)}>
      {/* Scanning line */}
      <motion.div
        className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-indigo-500 to-transparent"
        initial={{ top: "10%" }}
        animate={{ top: ["10%", "90%", "10%"] }}
        transition={{
          duration: 3,
          repeat: Infinity,
          ease: "linear",
        }}
      />
      {/* Document lines */}
      <div className="space-y-2">
        <div className="h-3 w-3/4 bg-muted-foreground/20 rounded" />
        <div className="h-3 w-full bg-muted-foreground/20 rounded" />
        <div className="h-3 w-2/3 bg-muted-foreground/20 rounded" />
        <div className="h-6 mt-4" />
        <div className="h-3 w-full bg-muted-foreground/20 rounded" />
        <div className="h-3 w-4/5 bg-muted-foreground/20 rounded" />
        <div className="h-3 w-1/2 bg-muted-foreground/20 rounded" />
      </div>
    </div>
  )
}

// Strategize card with logo and connected nodes
function StrategizeVisual({ className }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const logoRef = useRef<HTMLDivElement>(null)
  const node1Ref = useRef<HTMLDivElement>(null)
  const node2Ref = useRef<HTMLDivElement>(null)
  const node3Ref = useRef<HTMLDivElement>(null)
  const node4Ref = useRef<HTMLDivElement>(null)

  return (
    <div ref={containerRef} className={cn("relative h-40", className)}>
      {/* Top row of nodes */}
      <div className="absolute top-2 left-0 right-0 flex justify-center gap-8">
        <motion.div
          ref={node1Ref}
          className="w-10 h-10 rounded-lg bg-muted/50 border border-border/50 flex items-center justify-center"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 2, repeat: Infinity, delay: 0 }}
        >
          <FileText className="w-5 h-5 text-muted-foreground/60" />
        </motion.div>
        <motion.div
          ref={node2Ref}
          className="w-10 h-10 rounded-lg bg-muted/50 border border-border/50 flex items-center justify-center"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 2, repeat: Infinity, delay: 0.3 }}
        >
          <FileText className="w-5 h-5 text-muted-foreground/60" />
        </motion.div>
        <motion.div
          ref={node3Ref}
          className="w-10 h-10 rounded-lg bg-muted/50 border border-border/50 flex items-center justify-center"
          animate={{ y: [0, -3, 0] }}
          transition={{ duration: 2, repeat: Infinity, delay: 0.6 }}
        >
          <FileText className="w-5 h-5 text-muted-foreground/60" />
        </motion.div>
      </div>

      {/* Middle node */}
      <motion.div
        ref={node4Ref}
        className="absolute top-14 left-1/4 w-10 h-10 rounded-lg bg-muted/50 border border-border/50 flex items-center justify-center"
        animate={{ y: [0, -3, 0] }}
        transition={{ duration: 2, repeat: Infinity, delay: 0.9 }}
      >
        <FileText className="w-5 h-5 text-muted-foreground/60" />
      </motion.div>

      {/* Bar graph section */}
      <div className="absolute bottom-0 left-0 right-0">
        <AnimatedBarGraph />
      </div>

      {/* Logo in center-bottom */}
      <motion.div
        ref={logoRef}
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
        animate={{ scale: [1, 1.05, 1] }}
        transition={{ duration: 3, repeat: Infinity }}
      >
        <img src="/logo-new.svg" alt="OmniDome" className="w-8 h-8" />
      </motion.div>

      {/* Animated beams */}
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={node1Ref}
        toRef={logoRef}
        curvature={20}
        gradientStartColor="#6366f1"
        gradientStopColor="#06b6d4"
        pathColor="rgba(99, 102, 241, 0.5)"
        duration={3}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={node2Ref}
        toRef={logoRef}
        curvature={10}
        gradientStartColor="#8b5cf6"
        gradientStopColor="#06b6d4"
        pathColor="rgba(139, 92, 246, 0.5)"
        duration={3.5}
        delay={0.5}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={node3Ref}
        toRef={logoRef}
        curvature={20}
        gradientStartColor="#a855f7"
        gradientStopColor="#06b6d4"
        pathColor="rgba(168, 85, 247, 0.5)"
        duration={4}
        delay={1}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={node4Ref}
        toRef={logoRef}
        curvature={-10}
        gradientStartColor="#6366f1"
        gradientStopColor="#22d3ee"
        pathColor="rgba(99, 102, 241, 0.5)"
        duration={3.2}
        delay={0.7}
      />
    </div>
  )
}

// Research card with animated beams connecting to document
function ResearchVisual({ className }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const docRef = useRef<HTMLDivElement>(null)
  const source1Ref = useRef<HTMLDivElement>(null)
  const source2Ref = useRef<HTMLDivElement>(null)
  const source3Ref = useRef<HTMLDivElement>(null)

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      {/* Source indicators on the sides */}
      <motion.div
        ref={source1Ref}
        className="absolute top-4 left-0 w-2 h-2 rounded-full bg-indigo-500/50"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      <motion.div
        ref={source2Ref}
        className="absolute top-1/2 left-0 w-2 h-2 rounded-full bg-cyan-500/50"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 2, repeat: Infinity, delay: 0.5 }}
      />
      <motion.div
        ref={source3Ref}
        className="absolute bottom-4 left-0 w-2 h-2 rounded-full bg-purple-500/50"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 2, repeat: Infinity, delay: 1 }}
      />

      {/* Document */}
      <div ref={docRef} className="ml-6">
        <DocumentPreview />
      </div>

      {/* Animated beams from sources to document */}
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={source1Ref}
        toRef={docRef}
        gradientStartColor="#6366f1"
        gradientStopColor="#06b6d4"
        pathColor="rgba(99, 102, 241, 0.15)"
        duration={2.5}
        curvature={-20}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={source2Ref}
        toRef={docRef}
        gradientStartColor="#22d3ee"
        gradientStopColor="#8b5cf6"
        pathColor="rgba(34, 211, 238, 0.15)"
        duration={3}
        delay={0.3}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={source3Ref}
        toRef={docRef}
        gradientStartColor="#a855f7"
        gradientStopColor="#06b6d4"
        pathColor="rgba(168, 85, 247, 0.15)"
        duration={2.8}
        delay={0.6}
        curvature={20}
      />
    </div>
  )
}

// Engage card with checkmark animation
function EngageVisual({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center justify-center gap-3", className)}>
      {/* Document cards */}
      <motion.div
        className="w-16 h-20 rounded-lg bg-muted border border-border shadow-sm"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 2, repeat: Infinity }}
      />
      <motion.div
        className="relative w-20 h-24 rounded-lg bg-muted border border-border shadow-sm"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 2, repeat: Infinity, delay: 0.2 }}
      >
        {/* Success checkmark */}
        <motion.div
          className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center shadow-lg"
          initial={{ scale: 0 }}
          animate={{ scale: [0, 1.2, 1] }}
          transition={{ duration: 0.5, repeat: Infinity, repeatDelay: 3 }}
        >
          <Check className="w-4 h-4 text-white" />
        </motion.div>
      </motion.div>
      <motion.div
        className="w-16 h-20 rounded-lg bg-muted border border-border shadow-sm"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 2, repeat: Infinity, delay: 0.4 }}
      />
    </div>
  )
}

// Step Arrow Component
function StepArrow({ step, direction = "down" }: { step: number; direction?: "down" | "up" }) {
  return (
    <div className={cn(
      "flex items-center gap-2 text-sm text-muted-foreground",
      direction === "up" && "flex-row-reverse"
    )}>
      <span className="font-medium">Step {step}</span>
      <motion.div
        animate={{ 
          y: direction === "down" ? [0, 5, 0] : [0, -5, 0],
        }}
        transition={{ duration: 1.5, repeat: Infinity }}
      >
        <svg 
          width="24" 
          height="24" 
          viewBox="0 0 24 24" 
          fill="none" 
          stroke="currentColor" 
          strokeWidth="2"
          className={cn(direction === "up" && "rotate-180")}
        >
          <path d="M12 5v14M19 12l-7 7-7-7" />
        </svg>
      </motion.div>
    </div>
  )
}

export function HowItWorks({ className }: { className?: string }) {
  return (
    <section className={cn("py-24 px-4 sm:px-6 lg:px-8", className)}>
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="text-center mb-16">
          <motion.p
            className="text-sm font-medium text-emerald-500 tracking-widest uppercase mb-4"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            How it works
          </motion.p>
          <motion.h2
            className="text-4xl sm:text-5xl font-bold text-foreground"
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.1 }}
          >
            AI-Powered Sales Intelligence in 3 Steps
          </motion.h2>
        </div>

        {/* Steps Grid */}
        <div className="relative grid md:grid-cols-3 gap-8">
          {/* Step 1 - Research */}
          <motion.div
            className="relative"
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.2 }}
          >
            {/* Step indicator */}
            <div className="absolute -top-10 left-8">
              <StepArrow step={1} />
            </div>
            
            <div className="bg-card rounded-2xl border border-border p-6 h-full hover:border-indigo-500/30 hover:shadow-lg hover:shadow-indigo-500/5 transition-all group">
              <h3 className="text-xl font-bold mb-6 text-foreground">Research</h3>
              <ResearchVisual className="mb-6 h-48" />
              <p className="text-sm text-muted-foreground">
                Train an AI agent that understands your ICP, differentiators and market landscape
              </p>
            </div>
          </motion.div>

          {/* Step 2 - Strategize */}
          <motion.div
            className="relative"
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.3 }}
          >
            {/* Step indicator */}
            <div className="absolute -bottom-10 left-1/2 -translate-x-1/2">
              <StepArrow step={2} direction="up" />
            </div>
            
            <div className="bg-card rounded-2xl border border-border p-6 h-full hover:border-cyan-500/30 hover:shadow-lg hover:shadow-cyan-500/5 transition-all group">
              <h3 className="text-xl font-bold mb-6 text-foreground">Strategize</h3>
              <StrategizeVisual className="mb-6" />
              <p className="text-sm text-muted-foreground">
                Connect the dots between your specific solution and the prospect's needs
              </p>
            </div>
          </motion.div>

          {/* Step 3 - Engage */}
          <motion.div
            className="relative"
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: 0.4 }}
          >
            {/* Step indicator */}
            <div className="absolute -top-10 right-8">
              <StepArrow step={3} />
            </div>
            
            <div className="bg-card rounded-2xl border border-border p-6 h-full hover:border-emerald-500/30 hover:shadow-lg hover:shadow-emerald-500/5 transition-all group">
              <h3 className="text-xl font-bold mb-6 text-foreground">Engage</h3>
              <EngageVisual className="mb-6 h-48" />
              <p className="text-sm text-muted-foreground">
                Build strategic account plans and ready-to-use deliverables in minutes
              </p>
            </div>
          </motion.div>

          {/* Connecting line between cards (desktop only) */}
          <div className="hidden md:block absolute top-1/2 left-0 right-0 h-0.5 -z-10">
            <motion.div
              className="h-full bg-gradient-to-r from-indigo-500/20 via-cyan-500/30 to-emerald-500/20"
              initial={{ scaleX: 0 }}
              whileInView={{ scaleX: 1 }}
              viewport={{ once: true }}
              transition={{ duration: 1, delay: 0.5 }}
            />
          </div>
        </div>
      </div>
    </section>
  )
}
