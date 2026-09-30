"use client"

import React from "react"

const CSP = "default-src 'none'; img-src data: https:; style-src 'unsafe-inline'; font-src data: https:"

/** Wrap untrusted HTML in a document whose CSP forbids scripts, frames, forms and network fetches. */
export function buildPreviewDoc(html: string): string {
  return (
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${CSP}">` +
    `<base target="_blank"><style>body{margin:0;padding:24px;font:14px/1.6 system-ui,sans-serif;color:#18181b;background:#fff;word-wrap:break-word}img{max-width:100%;height:auto}</style>` +
    `</head><body>${html}</body></html>`
  )
}

/** Plain-text excerpt of untrusted HTML (never rendered as markup). */
export function htmlToExcerpt(html: string, max = 180): string {
  return (html || "")
    .replace(/<(script|style|svg)[\s\S]*?<\/\1>/gi, " ")
    .replace(/<[^>]*>?/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, max)
}

/**
 * Renders untrusted template/email HTML in a fully sandboxed iframe: no allow-scripts and no
 * allow-same-origin, so it cannot run code or read this origin's localStorage (Supabase token).
 */
export function SandboxedEmailPreview({ html, className }: { html: string; className?: string }) {
  return (
    <iframe
      title="Email preview"
      sandbox=""
      referrerPolicy="no-referrer"
      srcDoc={buildPreviewDoc(html || "")}
      className={className ?? "w-full h-[50vh] bg-white rounded border-0"}
    />
  )
}
