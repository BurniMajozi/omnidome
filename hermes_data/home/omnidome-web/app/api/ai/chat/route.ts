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

  const openRouterKey = process.env.OPENROUTER_API_KEY
  const isOpenRouter = !!openRouterKey

  const baseUrl = isOpenRouter
    ? "https://openrouter.ai/api/v1"
    : (process.env.OLLAMA_BASE_URL || "http://127.0.0.1:11434")

  const defaultModel = isOpenRouter
    ? (process.env.OPENROUTER_MODEL || "owal-alpha")
    : (process.env.OLLAMA_MODEL || "qwen2.5-coder:14b")

  const model = body.model || defaultModel
  const temperature = typeof body.temperature === "number" ? body.temperature : 0.2
  const incomingMessages = Array.isArray(body.messages) ? body.messages : []

  if (!incomingMessages.length) {
    return NextResponse.json({ error: "No messages provided" }, { status: 400 })
  }

  const systemPrompt = body.system?.trim()
  const messages: ChatMessage[] = systemPrompt
    ? [{ role: "system", content: systemPrompt }, ...incomingMessages]
    : incomingMessages

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }

  if (isOpenRouter) {
    headers["Authorization"] = `Bearer ${openRouterKey}`
    headers["HTTP-Referer"] = "http://localhost:3000"
    headers["X-Title"] = "OmniDome"
  }

  const fetchUrl = isOpenRouter ? `${baseUrl}/chat/completions` : `${baseUrl}/api/chat`
  const fetchBody = isOpenRouter
    ? {
        model,
        messages,
        temperature,
      }
    : {
        model,
        messages,
        stream: false,
        options: { temperature },
      }

  let response: Response
  try {
    response = await fetch(fetchUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(fetchBody),
    })
  } catch (err) {
    return NextResponse.json(
      { error: `Failed to reach ${isOpenRouter ? "OpenRouter" : "Ollama"} server`, details: String(err) },
      { status: 502 },
    )
  }

  if (!response.ok) {
    const details = await response.text()
    return NextResponse.json(
      { error: `${isOpenRouter ? "OpenRouter" : "Ollama"} error (${response.status})`, details },
      { status: 502 },
    )
  }

  const data = await response.json()
  const message = data?.choices?.[0]?.message?.content ?? data?.message?.content ?? data?.response ?? ""
  return NextResponse.json({ message })
}
