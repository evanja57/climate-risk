"use client"

import { useCallback } from "react"

export type SourcesMap = Record<string, { url: string; label?: string }>

const citationRe = /\[(\d+)\]/g

export function SourceAwareText({
  text,
  sources,
}: { text?: string; sources?: SourcesMap }) {
  if (!text) return null

  // Split by capture group; even indexes = plain text, odd indexes = the number
  const parts = text.split(citationRe)

  const jump = useCallback((id: string) => {
    const el = document.getElementById(`source-${id}`)
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "start" })
    el.classList.add("ring-2", "ring-primary/60", "rounded-md")
    setTimeout(() => el.classList.remove("ring-2", "ring-primary/60", "rounded-md"), 1600)
  }, [])

  return (
    <span>
      {parts.map((seg, i) => {
        const isRef = i % 2 === 1
        if (!isRef) return <span key={i}>{seg}</span>
        const s = sources?.[seg]
        if (!s) return <sup key={i} className="ml-0.5 align-super">[{seg}]</sup>
        return (
          <sup key={i} className="ml-0.5 align-super">
            <button
              type="button"
              onClick={() => jump(seg)}
              className="text-primary underline hover:text-primary/80 focus-visible:outline-none focus-visible:ring focus-visible:ring-primary/60 rounded-sm"
              aria-label={`Jump to source ${seg}`}
            >
              [{seg}]
            </button>
          </sup>
        )
      })}
    </span>
  )
}
