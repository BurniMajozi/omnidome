import { useEffect, useState } from "react"

type ModuleDataResponse<T> = {
  data: T | null
  updated_at?: string | null
}

export function useModuleData<T>(moduleId: string, fallback: T) {
  const [data, setData] = useState<T>(fallback)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const response = await fetch(`/api/modules/${encodeURIComponent(moduleId)}`, {
          cache: "no-store",
        })
        if (!response.ok) {
          throw new Error(`Module data fetch failed: ${response.status}`)
        }
        const payload = (await response.json()) as ModuleDataResponse<T>
        if (!cancelled && payload && payload.data) {
          setData(payload.data)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Module data fetch failed")
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [moduleId])

  return { data, loading, error }
}
