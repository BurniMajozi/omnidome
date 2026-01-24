"use client"

import { cn } from "@/lib/utils"
import { AnimatedBeam, Circle } from "@/components/ui/animated-beam"
import { useRef } from "react"
import { Wifi, Users, Receipt, Phone, Megaphone, DollarSign } from "lucide-react"

export function AnimatedBeamMultipleOutputDemo({ className }: { className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const div1Ref = useRef<HTMLDivElement>(null)
  const div2Ref = useRef<HTMLDivElement>(null)
  const div3Ref = useRef<HTMLDivElement>(null)
  const div4Ref = useRef<HTMLDivElement>(null)
  const div5Ref = useRef<HTMLDivElement>(null)
  const div6Ref = useRef<HTMLDivElement>(null)
  const div7Ref = useRef<HTMLDivElement>(null)

  return (
    <div
      className={cn(
        "relative flex h-full w-full items-center justify-center overflow-hidden rounded-lg p-10",
        className
      )}
      ref={containerRef}
    >
      <div className="flex h-full max-h-[400px] w-full max-w-xl flex-row items-stretch justify-between gap-16">
        <div className="flex flex-col justify-center gap-4">
          <Circle ref={div1Ref}>
            <Users className="h-6 w-6 text-indigo-400" />
          </Circle>
          <Circle ref={div2Ref}>
            <Receipt className="h-6 w-6 text-green-400" />
          </Circle>
          <Circle ref={div3Ref}>
            <Phone className="h-6 w-6 text-blue-400" />
          </Circle>
          <Circle ref={div4Ref}>
            <Megaphone className="h-6 w-6 text-purple-400" />
          </Circle>
          <Circle ref={div5Ref}>
            <DollarSign className="h-6 w-6 text-emerald-400" />
          </Circle>
        </div>
        <div className="flex flex-col justify-center">
          <Circle ref={div6Ref} className="size-20">
            <img src="/logo-new.svg" alt="OmniDome" className="h-10 w-10" />
          </Circle>
        </div>
        <div className="flex flex-col justify-center">
          <Circle ref={div7Ref}>
            <Wifi className="h-6 w-6 text-cyan-400" />
          </Circle>
        </div>
      </div>

      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div1Ref}
        toRef={div6Ref}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div2Ref}
        toRef={div6Ref}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div3Ref}
        toRef={div6Ref}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div4Ref}
        toRef={div6Ref}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div5Ref}
        toRef={div6Ref}
      />
      <AnimatedBeam
        containerRef={containerRef}
        fromRef={div6Ref}
        toRef={div7Ref}
      />
    </div>
  )
}
