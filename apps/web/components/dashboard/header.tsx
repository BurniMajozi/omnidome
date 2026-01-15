"use client"

import React, { useState, useEffect } from "react"
import { Bell, Search, Plus, Sun, Moon } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { useTheme } from "next-themes"

interface HeaderProps {
  title: string
  onNewTask: () => void
}

export function Header({ title, onNewTask }: HeaderProps) {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = useState(false)

  // Avoid hydration mismatch by waiting for component to mount
  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <h1 className="text-xl font-bold tracking-tight text-foreground">{title}</h1>

      <div className="flex items-center gap-4">
        <div className="relative hidden md:block">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search anything..." className="h-10 w-64 bg-secondary/50 border-border pl-9 text-sm focus:border-primary/50 transition-all" />
        </div>

        <Button
          variant="ghost"
          size="icon"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
          className="text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
          title="Toggle theme"
        >
          {!mounted ? (
            <div className="h-5 w-5 animate-pulse rounded-full bg-muted" />
          ) : resolvedTheme === "dark" ? (
            <Sun className="h-5 w-5 transition-all text-amber-400" />
          ) : (
            <Moon className="h-5 w-5 transition-all text-indigo-500" />
          )}
          <span className="sr-only">Toggle theme</span>
        </Button>

        <Button variant="ghost" size="icon" className="relative text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors" title="Notifications">
          <Bell className="h-5 w-5" />
          <span className="absolute right-2.5 top-2.5 h-2 w-2 rounded-full bg-primary shadow-[0_0_10px_rgba(79,70,229,0.5)]" />
        </Button>

        <Button size="sm" className="gap-2" onClick={onNewTask}>
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">New Task</span>
        </Button>
      </div>
    </header>
  )
}
