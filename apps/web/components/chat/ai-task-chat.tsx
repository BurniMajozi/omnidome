"use client"

import type React from "react"

import { useState, useRef, useEffect } from "react"
import { X, Send, Mic, MessageCircle, Upload, FileText, LinkIcon, ImageIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  type: "text" | "voice" | "file"
  attachments?: Array<{ type: string; name: string; url?: string }>
}

interface AITaskChatProps {
  isOpen: boolean
  onClose: () => void
}

export function AITaskChat({ isOpen, onClose }: AITaskChatProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState("")
  const [interactionMode, setInteractionMode] = useState<"type" | "voice" | "converse" | null>(null)
  const [isRecording, setIsRecording] = useState(false)
  const [attachments, setAttachments] = useState<File[]>([])
  const [linkInput, setLinkInput] = useState("")
  const [showLinkInput, setShowLinkInput] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const imageInputRef = useRef<HTMLInputElement>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    if (!isOpen) {
      setInteractionMode(null)
      setMessages([])
      setAttachments([])
      setInputValue("")
      setShowLinkInput(false)
    }
  }, [isOpen])

  const handleSendMessage = async () => {
    if (!inputValue.trim() && attachments.length === 0) return

    const newMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: inputValue,
      type: interactionMode === "voice" ? "voice" : "text",
      attachments: attachments.map((file) => ({
        type: file.type,
        name: file.name,
      })),
    }

    setMessages((prev) => [...prev, newMessage])
    setInputValue("")
    setAttachments([])

    // Simulate AI response
    setTimeout(() => {
      const aiMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `I'll help you create a task based on: "${inputValue}". This task will be processed and added to your dashboard.`,
        type: "text",
      }
      setMessages((prev) => [...prev, aiMessage])
    }, 500)
  }

  const handleStartRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      mediaRecorderRef.current = mediaRecorder

      const audioChunks: Blob[] = []
      mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data)
      }

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: "audio/wav" })
        const file = new File([audioBlob], `audio-${Date.now()}.wav`, { type: "audio/wav" })
        setAttachments((prev) => [...prev, file])
      }

      mediaRecorder.start()
      setIsRecording(true)
    } catch (error) {
      console.error("Error accessing microphone:", error)
    }
  }

  const handleStopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      mediaRecorderRef.current.stream.getTracks().forEach((track) => track.stop())
      setIsRecording(false)
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.currentTarget.files
    if (files) {
      setAttachments((prev) => [...prev, ...Array.from(files)])
    }
    e.currentTarget.value = ""
  }

  const handleAddLink = () => {
    if (linkInput.trim()) {
      setInputValue((prev) => (prev ? `${prev} ${linkInput}` : linkInput))
      setLinkInput("")
      setShowLinkInput(false)
    }
  }

  const removeAttachment = (index: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== index))
  }

  if (!isOpen) return null

  return (
    <div className="flex h-screen w-80 flex-shrink-0 flex-col border-l border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-secondary p-4">
        <div>
          <h3 className="font-semibold text-foreground">Add Task</h3>
          <p className="text-xs text-muted-foreground">AI-powered task creation</p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={onClose}
          className="h-8 w-8 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Interaction Mode Selection */}
      {!interactionMode && messages.length === 0 && (
        <div className="flex flex-col gap-3 p-4">
          <p className="text-sm text-muted-foreground">Choose how you'd like to create a task:</p>
          <Button onClick={() => setInteractionMode("type")} className="justify-start gap-2" variant="outline">
            <MessageCircle className="h-4 w-4" />
            Type your task
          </Button>
          <Button onClick={() => setInteractionMode("voice")} className="justify-start gap-2" variant="outline">
            <Mic className="h-4 w-4" />
            Voice Chat
          </Button>
          <Button onClick={() => setInteractionMode("converse")} className="justify-start gap-2" variant="outline">
            <MessageCircle className="h-4 w-4" />
            Converse with AI
          </Button>
        </div>
      )}

      {/* Messages Area */}
      {interactionMode && (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center text-center">
                <div>
                  <MessageCircle className="mx-auto mb-2 h-8 w-8 text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">Start your conversation...</p>
                </div>
              </div>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={cn("flex gap-2", message.role === "user" ? "justify-end" : "justify-start")}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-lg px-3 py-2 text-sm",
                    message.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary text-foreground",
                  )}
                >
                  <p>{message.content}</p>
                  {message.attachments && message.attachments.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {message.attachments.map((attachment, idx) => (
                        <div
                          key={idx}
                          className={cn(
                            "flex items-center gap-2 text-xs",
                            message.role === "user" ? "text-primary-foreground/70" : "text-muted-foreground",
                          )}
                        >
                          <FileText className="h-3 w-3" />
                          {attachment.name}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Attachments Preview */}
          {attachments.length > 0 && (
            <div className="border-t border-border bg-secondary p-3">
              <div className="space-y-2">
                {attachments.map((file, idx) => (
                  <div key={idx} className="flex items-center justify-between rounded bg-background p-2 text-xs">
                    <span className="truncate text-muted-foreground">{file.name}</span>
                    <button
                      onClick={() => removeAttachment(idx)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Link Input */}
          {showLinkInput && (
            <div className="border-t border-border bg-secondary p-3">
              <div className="flex gap-2">
                <Input
                  value={linkInput}
                  onChange={(e) => setLinkInput(e.target.value)}
                  placeholder="Paste URL here..."
                  className="flex-1 text-sm"
                  onKeyPress={(e) => e.key === "Enter" && handleAddLink()}
                />
                <Button size="sm" onClick={handleAddLink}>
                  Add
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowLinkInput(false)}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          {/* Input Area */}
          <div className="space-y-3 border-t border-border p-4">
            {/* Text Input */}
            <div className="flex gap-2">
              <Input
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                placeholder={interactionMode === "voice" ? "Add notes or press Record..." : "Describe your task..."}
                className="flex-1"
              />
              <Button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() && attachments.length === 0}
                size="icon"
                className="shrink-0"
              >
                <Send className="h-4 w-4" />
              </Button>
            </div>

            {/* File Upload Options */}
            <div className="flex gap-2">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileUpload}
                className="hidden"
                accept=".pdf,.doc,.docx,.txt"
              />
              <input
                ref={imageInputRef}
                type="file"
                multiple
                onChange={handleFileUpload}
                className="hidden"
                accept="image/*"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                className="flex-1 gap-1 text-xs"
              >
                <Upload className="h-3 w-3" />
                Docs
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => imageInputRef.current?.click()}
                className="flex-1 gap-1 text-xs"
              >
                <ImageIcon className="h-3 w-3" />
                Image
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="flex-1 gap-1 text-xs bg-transparent"
                onClick={() => setShowLinkInput(true)}
              >
                <LinkIcon className="h-3 w-3" />
                Link
              </Button>
              {interactionMode === "voice" && (
                <Button
                  variant={isRecording ? "destructive" : "outline"}
                  size="sm"
                  onClick={isRecording ? handleStopRecording : handleStartRecording}
                  className="flex-1 gap-1 text-xs"
                >
                  <Mic className="h-3 w-3" />
                  {isRecording ? "Stop" : "Rec"}
                </Button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
