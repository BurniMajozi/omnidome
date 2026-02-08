"use client"

import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"
import { motion, AnimatePresence } from "framer-motion"

interface Message {
  id: number
  sender: "user" | "ai"
  name: string
  message: string
  typing?: boolean
}

const conversation: Message[] = [
  {
    id: 1,
    sender: "user",
    name: "Siyabonga",
    message: "Hey, can you check my calendar for tomorrow?",
  },
  {
    id: 2,
    sender: "ai",
    name: "Dome Agent",
    message: "Hi Siyabonga! 👋 Let me check your schedule for tomorrow...",
  },
  {
    id: 3,
    sender: "ai",
    name: "Dome Agent",
    message: "You have 3 appointments:\n• 09:00 - Fibre installation at 42 Main Rd\n• 11:30 - Client call with Vodacom\n• 14:00 - Team sync meeting",
  },
  {
    id: 4,
    sender: "user",
    name: "Siyabonga",
    message: "Can you reschedule the 11:30 call to 15:00?",
  },
  {
    id: 5,
    sender: "ai",
    name: "Dome Agent",
    message: "Done! ✅ I've moved your Vodacom call to 15:00. I've also sent a calendar update to all participants.",
  },
]

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-2 py-1">
      <motion.div
        className="w-2 h-2 rounded-full bg-indigo-400"
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1, repeat: Infinity, delay: 0 }}
      />
      <motion.div
        className="w-2 h-2 rounded-full bg-indigo-400"
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1, repeat: Infinity, delay: 0.2 }}
      />
      <motion.div
        className="w-2 h-2 rounded-full bg-indigo-400"
        animate={{ opacity: [0.4, 1, 0.4] }}
        transition={{ duration: 1, repeat: Infinity, delay: 0.4 }}
      />
    </div>
  )
}

function ChatMessage({ message, isNew }: { message: Message; isNew: boolean }) {
  const isUser = message.sender === "user"
  
  return (
    <motion.div
      initial={isNew ? { opacity: 0, y: 20, scale: 0.95 } : false}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={cn(
        "flex gap-2 max-w-[90%]",
        isUser ? "ml-auto flex-row-reverse" : "mr-auto"
      )}
    >
      {/* Avatar */}
      <div className={cn(
        "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold",
        isUser 
          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" 
          : "bg-indigo-500/20 text-indigo-400 border border-indigo-500/30"
      )}>
        {isUser ? (
          <span>S</span>
        ) : (
          <svg viewBox="0 0 24 24" className="w-5 h-5" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
          </svg>
        )}
      </div>
      
      {/* Message bubble */}
      <div className={cn(
        "rounded-2xl px-3 py-2",
        isUser 
          ? "bg-emerald-500/10 border border-emerald-500/20" 
          : "bg-slate-800/80 border border-slate-700/50"
      )}>
        <div className="flex items-center gap-2 mb-1">
          <span className={cn(
            "text-xs font-semibold",
            isUser ? "text-emerald-400" : "text-indigo-400"
          )}>
            {message.name}
          </span>
          {!isUser && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              AI
            </span>
          )}
        </div>
        <p className="text-sm text-slate-200 whitespace-pre-line leading-relaxed">
          {message.message}
        </p>
      </div>
    </motion.div>
  )
}

export function AIChatDemo({ className }: { className?: string }) {
  const [visibleMessages, setVisibleMessages] = useState<Message[]>([])
  const [isTyping, setIsTyping] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (currentIndex >= conversation.length) {
      const resetTimer = setTimeout(() => {
        setVisibleMessages([])
        setCurrentIndex(0)
        setIsTyping(false)
      }, 4000)
      return () => clearTimeout(resetTimer)
    }

    const nextMessage = conversation[currentIndex]
    const typingTimer = setTimeout(() => {
      if (nextMessage.sender === "ai") {
        setIsTyping(true)
      }
    }, 0)

    const messageTimer = setTimeout(() => {
      setIsTyping(false)
      setVisibleMessages(prev => [...prev, nextMessage])
      setCurrentIndex(prev => prev + 1)
    }, nextMessage.sender === "ai" ? 1500 : 1000)

    return () => {
      clearTimeout(typingTimer)
      clearTimeout(messageTimer)
    }
  }, [currentIndex])

  return (
    <div className={cn("relative flex h-full w-full flex-col", className)}>
      {/* Chat header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-slate-700/50 bg-slate-900/50">
        <div className="relative">
          <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
            <svg viewBox="0 0 24 24" className="w-5 h-5 text-indigo-400" fill="currentColor">
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
            </svg>
          </div>
          <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-500 border-2 border-slate-900" />
        </div>
        <div>
          <h4 className="text-sm font-semibold text-white">Dome Agent</h4>
          <p className="text-xs text-emerald-400">Online</p>
        </div>
      </div>
      
      {/* Messages */}
      <div className="flex-1 overflow-hidden p-4 space-y-3">
        <AnimatePresence mode="popLayout">
          {visibleMessages.map((msg, idx) => (
            <ChatMessage 
              key={msg.id} 
              message={msg} 
              isNew={idx === visibleMessages.length - 1}
            />
          ))}
        </AnimatePresence>
        
        {/* Typing indicator */}
        {isTyping && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="flex gap-2 items-center"
          >
            <div className="w-8 h-8 rounded-full bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center">
              <svg viewBox="0 0 24 24" className="w-5 h-5 text-indigo-400" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
              </svg>
            </div>
            <div className="rounded-2xl px-3 py-2 bg-slate-800/80 border border-slate-700/50">
              <TypingIndicator />
            </div>
          </motion.div>
        )}
      </div>
      
      {/* Input bar (decorative) */}
      <div className="px-4 py-3 border-t border-slate-700/50 bg-slate-900/30">
        <div className="flex items-center gap-2 px-3 py-2 rounded-full bg-slate-800/50 border border-slate-700/50">
          <span className="text-sm text-slate-500 flex-1">Ask Dome Agent...</span>
          <div className="w-8 h-8 rounded-full bg-indigo-500 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </div>
        </div>
      </div>
    </div>
  )
}
