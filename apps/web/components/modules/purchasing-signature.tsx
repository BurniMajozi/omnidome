"use client"

import { useRef } from "react"
import { Button } from "@/components/ui/button"

export function PurchasingSignature({ onChange }: { onChange: (png: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const drawing = useRef(false)
  const marked = useRef(false)
  return (
    <div className="space-y-2">
      <canvas
        ref={canvas} width={560} height={160}
        className="w-full rounded border bg-white touch-none"
        aria-label="Draw your approval signature"
        onPointerDown={(event) => {
          const target = canvas.current!
          const bounds = target.getBoundingClientRect()
          const context = target.getContext("2d")!
          context.beginPath()
          context.moveTo((event.clientX - bounds.left) * target.width / bounds.width, (event.clientY - bounds.top) * target.height / bounds.height)
          context.lineWidth = 2
          context.lineCap = "round"
          context.strokeStyle = "#111827"
          drawing.current = true
          target.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drawing.current) return
          const target = canvas.current!
          const bounds = target.getBoundingClientRect()
          const context = target.getContext("2d")!
          context.lineTo((event.clientX - bounds.left) * target.width / bounds.width, (event.clientY - bounds.top) * target.height / bounds.height)
          context.stroke()
          marked.current = true
        }}
        onPointerUp={() => {
          drawing.current = false
          if (marked.current) onChange(canvas.current!.toDataURL("image/png"))
        }}
        onPointerCancel={() => { drawing.current = false }}
      />
      <Button type="button" variant="outline" size="sm" onClick={() => {
        canvas.current?.getContext("2d")?.clearRect(0, 0, 560, 160)
        marked.current = false
        onChange("")
      }}>Clear signature</Button>
    </div>
  )
}
