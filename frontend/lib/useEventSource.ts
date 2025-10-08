import { useEffect } from "react"

export type EventHandler<T = any> = (data: T) => void

export function useEventSource(
  url: string | null,
  onMessage: EventHandler,
  onError?: EventHandler<Event>,
): void {
  useEffect(() => {
    if (!url) return
    const source = new EventSource(url, { withCredentials: false })

    source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data)
        onMessage(parsed)
      } catch (err) {
        console.error("Failed to parse SSE payload", err)
      }
    }

    if (onError) {
      source.onerror = (event) => {
        onError(event)
        source.close()
      }
    }

    return () => {
      source.close()
    }
  }, [url, onMessage, onError])
}
