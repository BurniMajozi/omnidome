// Artifact extraction shared by every agent chat. An artifact is a fenced block in an assistant reply (the
// canvas opens it beside the chat). Models do not always fence what is plainly a document, so a finished reply
// that looks like one (table, several headings, or very long) also gets a trailing "document" artifact instead
// of silently having no canvas.

export interface Artifact {
  msgId?: string
  id: string
  title: string
  lang: string
  code: string
}

export interface Segment {
  type: "text" | "artifact"
  value: string
}


const FENCE = /```([^\n\r`]+)?\n?([\s\S]*?)```/g

function extractArtifactTitle(code: string, langInfo: string, idx: number): string {
  const titleAttr = langInfo.match(/title=["']([^"']+)["']/i)
  if (titleAttr && titleAttr[1].trim()) {
    return titleAttr[1].trim()
  }

  const lines = code.trim().split("\n")
  for (let i = 0; i < Math.min(lines.length, 6); i++) {
    const line = lines[i].trim()
    const headingMatch = line.match(/^#{1,3}\s+([^#\n\r]+)/)
    if (headingMatch && headingMatch[1].trim()) {
      return headingMatch[1].trim().replace(/[*_`]/g, "")
    }
    const subjectMatch = line.match(/^Subject:\s*(.+)$/i)
    if (subjectMatch && subjectMatch[1].trim()) {
      return `Email: ${subjectMatch[1].trim()}`
    }
    const titleLineMatch = line.match(/^Title:\s*(.+)$/i)
    if (titleLineMatch && titleLineMatch[1].trim()) {
      return titleLineMatch[1].trim().replace(/[*_`]/g, "")
    }
  }

  const lower = code.toLowerCase()
  if (lower.includes("subject:") || lower.includes("dear ") || lower.includes("recipient:") || langInfo.includes("email")) {
    return `Email Draft (${idx + 1})`
  }
  if (lower.includes("slide ") || lower.includes("presentation") || lower.includes("agenda") || langInfo.includes("presentation") || langInfo.includes("deck")) {
    return `Presentation Outline (${idx + 1})`
  }
  if (lower.includes("strategy") || lower.includes("proposal") || lower.includes("action plan") || lower.includes("executive summary")) {
    return `Strategy Proposal (${idx + 1})`
  }
  if (langInfo.includes("sql") || lower.includes("select ") || lower.includes("from ")) {
    return `SQL Query (${idx + 1})`
  }

  return `Proposal Artifact ${idx + 1}`
}

/** An unfenced reply that is plainly a deliverable: a table, several headings, or a long write-up. */
export function looksLikeDocument(content: string): boolean {
  const text = content.trim()
  if (text.length < 400) return false
  const tableRows = (text.match(/^\s*\|.+\|\s*$/gm) || []).length
  const headings = (text.match(/^#{1,3}\s+\S/gm) || []).length
  const bold = (text.match(/^\s*\*\*[^*\n]+\*\*\s*$/gm) || []).length
  return tableRows >= 3 || headings >= 2 || bold >= 3 || text.length > 1800
}

export function parseMessage(msgId: string, content: string, allowImplicit = true): { segments: Segment[]; artifacts: Artifact[] } {
  const segments: Segment[] = []
  const artifacts: Artifact[] = []
  let last = 0
  let idx = 0
  let m: RegExpExecArray | null
  FENCE.lastIndex = 0
  while ((m = FENCE.exec(content)) !== null) {
    if (m.index > last) segments.push({ type: "text", value: content.slice(last, m.index) })
    const rawLang = (m[1] || "text").trim()
    const lang = rawLang.split(/[\s:]/)[0].toLowerCase() || "text"
    const code = m[2] ?? ""
    const id = `${msgId}-art-${idx}`
    const title = extractArtifactTitle(code, rawLang, idx)
    artifacts.push({ id, title, lang, code })
    segments.push({ type: "artifact", value: id })
    last = m.index + m[0].length
    idx += 1
  }
  if (last < content.length) segments.push({ type: "text", value: content.slice(last) })
  if (segments.length === 0) segments.push({ type: "text", value: content })
  if (allowImplicit && artifacts.length === 0 && looksLikeDocument(content)) {
    const id = `${msgId}-doc`
    artifacts.push({ id, title: extractArtifactTitle(content, "markdown", 0).replace(/^Proposal Artifact 1$/, "Response document"), lang: "markdown", code: content.trim() })
    segments.push({ type: "artifact", value: id })
  }
  return { segments, artifacts }
}

