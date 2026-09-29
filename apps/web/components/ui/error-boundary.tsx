"use client"

import React, { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertCircle, RefreshCw } from "lucide-react"
import { Button } from "./button"
import { Card, CardContent } from "./card"

interface Props {
  children?: ReactNode
  fallbackTitle?: string
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught client-side error:", error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      return (
        <Card className="border-red-500/30 bg-red-500/5 my-4">
          <CardContent className="p-6 text-center space-y-3">
            <div className="inline-flex p-3 rounded-full bg-red-500/10 text-red-400">
              <AlertCircle className="h-6 w-6" />
            </div>
            <h4 className="text-sm font-semibold text-foreground">
              {this.props.fallbackTitle || "Something went wrong in this section"}
            </h4>
            <p className="text-xs text-muted-foreground max-w-md mx-auto">
              {this.state.error?.message || "An unexpected error occurred while rendering."}
            </p>
            <Button
              size="sm"
              variant="outline"
              onClick={() => this.setState({ hasError: false, error: null })}
              className="text-xs gap-1.5"
            >
              <RefreshCw className="h-3 w-3" />
              Try Again
            </Button>
          </CardContent>
        </Card>
      )
    }

    return this.props.children
  }
}
