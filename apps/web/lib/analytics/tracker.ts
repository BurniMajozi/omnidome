"use client"

/**
 * OmniDome Web Analytics Tracker
 * Lightweight client-side tracking SDK.
 */

const ANALYTICS_ENDPOINT = "/api/analytics"
const BATCH_SIZE = 10
const FLUSH_INTERVAL = 5000

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
  private unsubmittedForms: Set<string> = new Set()

  constructor() {
    this.sessionId = this.getOrCreateId("omni_session", 1800)
    this.visitorId = this.getOrCreateId("omni_visitor", 365 * 86400)

    if (typeof window === "undefined") return

    this.currentPage = window.location.pathname
    this.setupFlushTimer()
    this.trackPageView()

    window.addEventListener("beforeunload", () => this.handlePageUnload())
    this.setupNavigationTracking()
    document.addEventListener("click", (e) => this.handleClick(e))
    this.setupFormTracking()
    this.setupScrollTracking()
  }

  private getOrCreateId(key: string, ttlSeconds: number): string {
    try {
      const stored = localStorage.getItem(key)
      if (stored) {
        try {
          const parsed = JSON.parse(stored)
          if (parsed?.expiry > Date.now()) return parsed.value
        } catch { /* corrupt */ }
      }
    } catch { /* no localStorage */ }
    const value = this.generateId()
    try {
      localStorage.setItem(key, JSON.stringify({ value, expiry: Date.now() + ttlSeconds * 1000 }))
    } catch { /* ignore */ }
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
        path,
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

  private handleClick(e: MouseEvent) {
    const target = e.target as HTMLElement
    if (!target || target.tagName === "HTML" || target.tagName === "BODY") return
    const tag = target.tagName.toLowerCase()

    this.queue.push({
      type: "click",
      data: {
        session_id: this.sessionId,
        visitor_id: this.visitorId,
        page_view_id: this.pageViewId,
        element_tag: tag,
        element_id: target.id || undefined,
        element_class: target.className?.substring(0, 300) || undefined,
        element_text: target.textContent?.trim().substring(0, 200) || undefined,
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
    const forms = document.querySelectorAll("form")

    const setupForm = (form: HTMLFormElement) => {
      const formId = form.id || form.getAttribute("name") || form.action || "unnamed-" + Math.random().toString(36).slice(2, 8)
      let started = false
      const fields = form.querySelectorAll("input, select, textarea")

      fields.forEach((field) => {
        field.addEventListener("focus", () => {
          if (!started) {
            started = true
            this.formStartTimes.set(formId, Date.now())
            this.formFieldInteracted.set(formId, new Set())
            this.unsubmittedForms.add(formId)

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
          const interacted = this.formFieldInteracted.get(formId)
          if (interacted) {
            const name = (field as HTMLInputElement).name || (field as HTMLInputElement).id || "unnamed"
            interacted.add(name)
          }
        })
      })

      form.addEventListener("submit", () => {
        const startTime = this.formStartTimes.get(formId)
        const interacted = this.formFieldInteracted.get(formId)
        const timeToComplete = startTime ? Math.round((Date.now() - startTime) / 1000) : undefined
        this.unsubmittedForms.delete(formId)

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
    }

    forms.forEach(setupForm)

    // Track abandons on page unload
    window.addEventListener("beforeunload", () => {
      this.unsubmittedForms.forEach((formId) => {
        const interacted = this.formFieldInteracted.get(formId)
        if (interacted && interacted.size > 0) {
          this.queue.push({
            type: "form",
            data: {
              session_id: this.sessionId,
              visitor_id: this.visitorId,
              page_view_id: this.pageViewId,
              form_id: formId,
              event_type: "abandon",
              fields_interacted: Array.from(interacted),
              path: this.currentPage,
            },
          })
        }
      })
      this.flush(true)
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
            this.maxScrollDepth = Math.max(this.maxScrollDepth, Math.round((scrollTop / docHeight) * 100))
          }
          ticking = false
        })
        ticking = true
      }
    }, { passive: true })
  }

  private handlePageUnload() {
    const timeOnPage = Math.round((Date.now() - this.pageStartTime) / 1000)
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
      data: { session_id: this.sessionId, duration_seconds: null },
    })
    this.flush(true)
  }

  private setupNavigationTracking() {
    if (typeof window === "undefined") return
    window.addEventListener("popstate", () => {
      this.handlePageUnload()
      this.pageStartTime = Date.now()
      this.maxScrollDepth = 0
      this.trackPageView()
    })
    const originalPushState = history.pushState
    history.pushState = (...args: Parameters<typeof history.pushState>) => {
      originalPushState.apply(history, args)
      this.handlePageUnload()
      this.pageStartTime = Date.now()
      this.maxScrollDepth = 0
      this.trackPageView()
    }
  }

  private setupFlushTimer() {
    this.flushTimer = setInterval(() => this.flush(), FLUSH_INTERVAL)
  }

  private flushIfFull() {
    if (this.queue.length >= BATCH_SIZE) this.flush()
  }

  private flush(sync = false) {
    if (this.queue.length === 0) return
    const events = this.queue.splice(0, BATCH_SIZE)

    for (const event of events) {
      const path = event.type === "session_end" ? "session/end" : event.type
      const endpoint = `${ANALYTICS_ENDPOINT}/track/${path}`
      const payload = JSON.stringify(event.data)

      if (sync && typeof navigator !== "undefined" && navigator.sendBeacon) {
        navigator.sendBeacon(endpoint, new Blob([payload], { type: "application/json" }))
      } else {
        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
          keepalive: true,
        }).then((res) => res.json()).then((data) => {
          if (data.page_view_id) this.pageViewId = data.page_view_id
        }).catch(() => { /* silent */ })
      }
    }
  }
}

let tracker: AnalyticsTracker | null = null

export function getAnalytics(): AnalyticsTracker | null {
  if (typeof window === "undefined") return null
  if (!tracker) tracker = new AnalyticsTracker()
  return tracker
}

export function useAnalytics() {
  return getAnalytics()
}
