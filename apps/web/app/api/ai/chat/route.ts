import { NextResponse } from "next/server"

type ChatMessage = {
  role: "system" | "user" | "assistant"
  content: string
}

type ChatRequest = {
  messages?: ChatMessage[]
  system?: string
  model?: string
  temperature?: number
}

export async function POST(request: Request) {
  let body: ChatRequest
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 })
  }

  const baseUrl = process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434"
  const model = body.model || process.env.OLLAMA_MODEL || "qwen2.5-coder:14b"
  const temperature = typeof body.temperature === "number" ? body.temperature : 0.2
  const incomingMessages = Array.isArray(body.messages) ? body.messages : []

  if (!incomingMessages.length) {
    return NextResponse.json({ error: "No messages provided" }, { status: 400 })
  }

  const systemPrompt = body.system?.trim()
  const messages: ChatMessage[] = systemPrompt
    ? [{ role: "system", content: systemPrompt }, ...incomingMessages]
    : incomingMessages

  let response: Response
  try {
    response = await fetch(`${baseUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model,
        messages,
        stream: false,
        options: { temperature },
      }),
    })
  } catch {
    return NextResponse.json({ error: "Failed to reach Ollama server" }, { status: 502 })
  }

  if (!response.ok) {
    const details = await response.text()
    return NextResponse.json(
      { error: `Ollama error (${response.status})`, details },
      { status: 502 },
    )
  }

  const data = await response.json()
  const message = data?.message?.content ?? data?.response ?? ""
  return NextResponse.json({ message })
}
