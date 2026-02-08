"use client"

import * as React from "react"
import { Moon, Sun } from "lucide-react"
import { useTheme } from "next-themes"
import { cn } from "@/lib/utils"
import { useIsClient } from "@/lib/use-is-client"

export function ThemeToggle({ className }: { className?: string }) {
    const { resolvedTheme, setTheme } = useTheme()
    const isClient = useIsClient()

    if (!isClient) {
        return (
            <div className={cn("flex items-center gap-1 p-1 rounded-full bg-muted/50 border border-border", className)}>
                <div className="w-8 h-8" />
                <div className="w-8 h-8" />
            </div>
        )
    }

    return (
        <div className={cn("flex items-center gap-1 p-1 rounded-full bg-muted/50 border border-border backdrop-blur-sm", className)}>
            <button
                onClick={() => setTheme("light")}
                className={cn(
                    "p-2 rounded-full transition-all duration-200",
                    resolvedTheme === "light"
                        ? "bg-amber-500 text-white shadow-[0_0_10px_rgba(245,158,11,0.5)]"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
                title="Light mode"
            >
                <Sun className="h-4 w-4" />
            </button>
            <button
                onClick={() => setTheme("dark")}
                className={cn(
                    "p-2 rounded-full transition-all duration-200",
                    resolvedTheme === "dark"
                        ? "bg-indigo-500 text-white shadow-[0_0_10px_rgba(99,102,241,0.5)]"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
                title="Dark mode"
            >
                <Moon className="h-4 w-4" />
            </button>
        </div>
    )
}

// Compact version for tight spaces
export function ThemeToggleCompact({ className }: { className?: string }) {
    const { resolvedTheme, setTheme } = useTheme()
    const isClient = useIsClient()

    const toggleTheme = () => {
        setTheme(resolvedTheme === "dark" ? "light" : "dark")
    }

    if (!isClient) {
        return <div className={cn("w-9 h-9 rounded-full bg-slate-800/50 border border-slate-700/50", className)} />
    }

    return (
        <button
            onClick={toggleTheme}
            className={cn(
                "p-2 rounded-full transition-all duration-200 border",
                resolvedTheme === "light" && "bg-amber-500/10 border-amber-500/50 text-amber-500 hover:bg-amber-500/20",
                resolvedTheme === "dark" && "bg-indigo-500/10 border-indigo-500/50 text-indigo-400 hover:bg-indigo-500/20",
                className
            )}
            title={`Switch to ${resolvedTheme === "dark" ? "light" : "dark"} mode`}
        >
            {resolvedTheme === "light" && <Sun className="h-4 w-4" />}
            {resolvedTheme === "dark" && <Moon className="h-4 w-4" />}
        </button>
    )
}
