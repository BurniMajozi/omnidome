"use client"

/**
 * OmniDome Web Analytics Tracker
 *
 * Lightweight client-side tracking SDK that captures:
 * - Page views (with path, title, referrer, screen size)
 * - Clicks (element tag, id, class, text, href, position)
 * - Form interactions (view, start, submit, abandon, validation errors)
 * - Engagement (time on page, scroll depth)
 * - Session lifecycle (start, end)
 *
 * Events are batched and sent to the analytics backend.
 */

const ANALYTICS_ENDPOINT = process.env.NEXT_PUBLIC_ANALYTICS_ENDPOINT || "/api/analytics"
const BATCH_SIZE = 10
const FLUSH_INTERVAL = 5000 // ms

interface QueuedEvent {
  type: "pageview" | "click" | "form" | "session_end"
  data: Record<string, any>
}

class AnalyticsTracker {
  private sessionId: string
  private visitorId: string
  private pageViewId: string | null = null
  private queue: QueuedEvent[] = []
  private flushTimer: ReturnType<typeof setInterval> | null = null
  private pageStartTime: number = Date.now()
  private maxScrollDepth: number = 0
  private currentPage: string = ""
  private formStartTimes: Map<string, number> = new Map()
  private formFieldInteracted: Map<string, Set<string>> = new Map()

  constructor() {
    this.sessionId = this.getOrCreateId("omni_session", 1800) // 30 min TTL
    this.visitorId = this.getOrCreateId("omni_visitor", 365 * 86400) // 1 year

    if (typeof window === "undefined") return

    this.currentPage = window.location.pathname
    this.setupFlushTimer()
    this.trackPageView()

    // Track page unload
    window.addEventListener("beforeunload", () => this.handlePageUnload())

    // Track navigation (SPA support)
    this.setupNavigationTracking()

    // Track clicks
    document.addEventListener("click", (e) => this.handleClick(e))

    // Track forms
    this.setupFormTracking()

    // Track scroll depth
    this.setupScrollTracking()
  }

  // --- ID management ---

  private getOrCreateId(key: string, ttlSeconds: number): string {
    try {
      const stored = localStorage.getItem(key)
      if (stored) {
        try {
          const parsed = JSON.parse(stored)
          if (parsed && parsed.expiry && parsed.expiry > Date.now()) {
            return parsed.value
          }
        } catch {
          // corrupted — regenerate
        }
      }
    } catch {
      // localStorage unavailable
    }

    const value = this.generateId()
    try {
      localStorage.setItem(key, JSON.stringify({ value, expiry: Date.now() + ttlSeconds * 1000 }))
    } catch {
      // ignore
    }
    return value
  }

  private generateId(): string {
    const arr = new Uint8Array(16)
    if (typeof crypto !== "undefined" && crypto.getRandomValues) {
      crypto.getRandomValues(arr)
    } else {
      for (let i = 0; i < 16; i++) arr[i] = Math.floor(Math.random() * 256)
    }
    return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("")
  }

  // --- Public tracking methods ---

  trackPageView(overridePath?: string) {
    if (typeof window === "undefined") return

    this.pageStartTime = Date.now()
    this.maxScrollDepth = 0
    const path = overridePath || window.location.pathname + window.location.search

    const urlParams = new URLSearchParams(window.location.search)
    this.queue.push({
      type: "pageview",
      data: {
        session_id: this.sessionId,
        visitor_id: this.visitorId,
        url: window.location.href,
        path: path,
        title: document.title,
        referrer: document.referrer || undefined,
        screen_width: window.screen.width,
        screen_height: window.screen.height,
        utm_source: urlParams.get("utm_source") || undefined,
        utm_medium: urlParams.get("utm_medium") || undefined,
        utm_campaign: urlParams.get("utm_campaign") || undefined,
        utm_term: urlParams.get("utm_term") || undefined,
        utm_content: urlParams.get("utm_content") || undefined,
      },
    })
    this.currentPage = path
    this.flush()
  }

  trackEvent(name: string, properties?: Record<string, any>) {
    // Generic event tracking — sent as a click for now
    this.queue.push({
      type: "click",
      data: {
        session_id: this.sessionId,
        visitor_id: this.visitorId,
        page_view_id: this.pageViewId,
        element_tag: "custom",
        element_text: name,
        path: this.currentPage,
        ...properties,
      },
    })
    this.flushIfFull()
  }

  // --- Internal event handlers ---

  private handleClick(e: MouseEvent) {
    const target = e.target as HTMLElement
    if (!target || target.tagName === "HTML" || target.tagName === "BODY") return

    const tag = target.tagName.toLowerCase()
    const text = target.textContent?.trim().substring(0, 200) || undefined

    this.queue.push({
      type: "click",
      data: {
        session_id: this.sessionId,
        visitor_id: this.visitorId,
        page_view_id: this.pageViewId,
        element_tag: tag,
        element_id: target.id || undefined,
        element_class: target.className?.substring(0, 300) || undefined,
        element_text: text,
        href: (target as HTMLAnchorElement).href || target.closest("a")?.getAttribute("href") || undefined,
        x: e.clientX,
        y: e.clientY,
        path: window.location.pathname + window.location.search,
      },
    })
    this.flushIfFull()
  }

  private setupFormTracking() {
    if (typeof document === "undefined") return

    // Track form views
    const forms = document.querySelectorAll("form")
    forms.forEach((form) => {
      const formId = form.id || form.getAttribute("name") || form.action || "unnamed"

      // Track form start (first field focus)
      let started = false
      const fields = form.querySelectorAll("input, select, textarea")
      fields.forEach((field) => {
        field.addEventListener("focus", () => {
          if (!started) {
            started = true
            this.formStartTimes.set(formId, Date.now())
            this.formFieldInteracted.set(formId, new Set())

            this.queue.push({
              type: "form",
              data: {
                session_id: this.sessionId,
                visitor_id: this.visitorId,
                page_view_id: this.pageViewId,
                form_id: formId,
                form_name: form.getAttribute("name") || formId,
                form_action: form.action || undefined,
                event_type: "start",
                fields_interacted: [],
                fields_count: fields.length,
                path: window.location.pathname,
              },
            })
          }

          // Track field interaction
          const interacted = this.formFieldInteracted.get(formId)
          if (interacted) {
            const fieldName = (field as HTMLInputElement).name || (field as HTMLInputElement).id || "unnamed"
            interacted.add(fieldName)
          }
        }, { once: false })
      })

      // Track form submit
      form.addEventListener("submit", () => {
        const startTime = this.formStartTimes.get(formId)
        const interacted = this.formFieldInteracted.get(formId)
        const timeToComplete = startTime ? Math.round((Date.now() - startTime) / 1000) : undefined

        this.queue.push({
          type: "form",
          data: {
            session_id: this.sessionId,
            visitor_id: this.visitorId,
            page_view_id: this.pageViewId,
            form_id: formId,
            form_name: form.getAttribute("name") || formId,
            form_action: form.action || undefined,
            event_type: "submit",
            fields_interacted: interacted ? Array.from(interacted) : [],
            fields_count: fields.length,
            time_to_complete: timeToComplete,
            path: window.location.pathname,
          },
        })
        this.flush()
      })
    })

    // Track form abandons on page unload
    window.addEventListener("beforeunload", () => {
      this.formStartTimes.forEach((startTime, formId) => {
        const interacted = this.formFieldInteracted.get(formId)
        // Only track abandon if form was started but not submitted
        if (interacted && interacted.size > 0) {
          const event: QueuedEvent = {
            type: "form",
            data: {
              session_id: this.sessionId,
              visitor_id: this.visitorId,
              page_view_id: this.pageViewId,
              form_id: formId,
              form_name: formId,
              event_type: "abandon",
              fields_interacted: Array.from(interacted),
              path: this.currentPage,
            },
          }
          this.queue.push(event)
        }
      })
      this.flush(true) // synchronous-ish
    })
  }

  private setupScrollTracking() {
    let ticking = false
    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          const scrollTop = window.scrollY || document.documentElement.scrollTop
          const docHeight = document.documentElement.scrollHeight - document.documentElement.clientHeight
          if (docHeight > 0) {
            const depth = Math.round((scrollTop / docHeight) * 100)
            this.maxScrollDepth = Math.max(this.maxScrollDepth, depth)
          }
          ticking = false
        })
        ticking = true
      }
    }, { passive: true })
  }

  private handlePageUnload() {
    const timeOnPage = Math.round((Date.now() - this.pageStartTime) / 1000)

    // Send final page view update with engagement data
    this.queue.push({
      type: "pageview",
      data: {
        session_id: this.sessionId,
        visitor_id: this.visitorId,
        url: window.location.href,
        path: this.currentPage,
        title: document.title,
        time_on_page: timeOnPage,
        scroll_depth: this.maxScrollDepth,
      },
    })

    this.queue.push({
      type: "session_end",
      data: {
        session_id: this.sessionId,
        duration_seconds: null, // Could track total session duration
      },
    })

    this.flush(true)
  }

  private setupNavigationTracking() {
    // Intercept Next.js router navigation
    if (typeof window === "undefined") return

    // For Next.js App Router — listen to popstate
    window.addEventListener("popstate", () => {
      this.handlePageUnload()
      this.pageStartTime = Date.now()
      this.maxScrollDepth = 0
      this.trackPageView()
    })

    // Push state override for programmatic navigation
    const originalPushState = history.pushState
    history.pushState = (...args) => {
      originalPushState.apply(history, args)
      this.handlePageUnload()
      this.pageStartTime = Date.now()
      this.maxScrollDepth = 0
      this.trackPageView()
    }
  }

  // --- Queue management ---

  private setupFlushTimer() {
    this.flushTimer = setInterval(() => this.flush(), FLUSH_INTERVAL)
  }

  private flushIfFull() {
    if (this.queue.length >= BATCH_SIZE) {
      this.flush()
    }
  }

  private flush(sync = false) {
    if (this.queue.length === 0) return

    const events = this.queue.splice(0, BATCH_SIZE)

    for (const event of events) {
      const endpoint = `${ANALYTICS_ENDPOINT}/track/${event.type === "session_end" ? "session/end" : event.type}`

      const payload = JSON.stringify(event.data)

      if (sync && typeof navigator !== "undefined") {
        // Use sendBeacon for unload scenarios
        if (navigator.sendBeacon) {
          navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }))
        }
      } else {
        // Normal fetch
        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
          keepalive: true,
        }).catch(() => {
          // Silently fail — analytics should not break the app
        })
      }
    }

    // Update page_view_id from pageview responses
    const pageviewEvent = events.find((e) => e.type === "pageview")
    if (pageviewEvent && pageviewEvent.data) {
      // We'll get the page_view_id from the response
      fetch(`${ANALYTICS_ENDPOINT}/track/pageview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pageviewEvent.data),
        keepalive: true,
      }).then((res) => res.json()).then((data) => {
        if (data.page_view_id) {
          this.pageViewId = data.page_view_id
        }
      }).catch(() => {})
    }
  }
}

// Singleton
let tracker: AnalyticsTracker | null = null

export function getAnalytics(): AnalyticsTracker | null {
  if (typeof window === "undefined") return null
  if (!tracker) {
    tracker = new AnalyticsTracker()
  }
  return tracker
}

/** React hook to get the analytics tracker */
export function useAnalytics() {
  return getAnalytics()
}
