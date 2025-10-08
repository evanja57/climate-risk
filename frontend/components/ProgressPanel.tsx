"use client"

import React from "react"

type StageId =
  | "scope"
  | "aggregate_sources"
  | "rank_filter"
  | "convert_docs"
  | "synthesize"
  | "model_risk"
  | "finalize"

type StageState = "idle" | "start" | "end"

export type ProgressState = {
  current: StageId | "idle" | "done" | "error"
  stages: Record<StageId, StageState>
  progress?: { done: number; total: number }
  ticker: string[]
  artifacts: { name: string; url: string }[]
  headline?: string
  note?: string
}

const STAGE_ORDER: StageId[] = [
  "scope",
  "aggregate_sources",
  "rank_filter",
  "convert_docs",
  "synthesize",
  "model_risk",
  "finalize",
]

// Hide finalize plus the near-instant scope/rank phases to keep a focused four-step display.
const VISIBLE_STAGE_ORDER: StageId[] = STAGE_ORDER.filter((id) =>
  !["scope", "rank_filter", "finalize"].includes(id),
)

const STAGE_LABELS: Record<StageId, string> = {
  scope: "Scope",
  aggregate_sources: "Gather Evidence",
  rank_filter: "Filter Sources",
  convert_docs: "Prepare Docs",
  synthesize: "Draft Assessment",
  model_risk: "Model Risks",
  finalize: "Finalize",
}

export function ProgressPanel({ state }: { state: ProgressState }) {
  const { current, stages, progress, ticker, headline, note } = state

  return (
    <div className="w-full space-y-3">
      <div aria-live="polite" aria-atomic="true">
        <div className="text-lg font-semibold">
          {headline ?? "Preparing assessment…"}
        </div>
        {note && <div className="text-sm text-muted-foreground">{note}</div>}
      </div>

      <ol className="grid gap-2 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
        {VISIBLE_STAGE_ORDER.map((id) => {
          const status = stages[id]
          const isCurrent = current === id
          const isDone = status === "end"
          return (
            <li
              key={id}
              className={`rounded-xl border p-2 transition ${
                isDone
                  ? "border-emerald-500/60 bg-emerald-50"
                  : isCurrent
                  ? "border-primary/70 bg-primary/5"
                  : "border-border bg-background"
              }`}
            >
              <div className="text-xs uppercase tracking-wide text-muted-foreground">
                {STAGE_LABELS[id]}
              </div>
              <div className="text-sm font-medium">
                {isDone ? "Done" : isCurrent ? "In progress…" : "Waiting"}
              </div>
            </li>
          )
        })}
      </ol>

      {current === "convert_docs" && progress && progress.total > 0 && (
        <div className="w-full">
          <div className="text-sm mb-1 text-muted-foreground">
            processing {progress.done}/{progress.total} documents…
          </div>
          <div className="h-2 w-full rounded-full bg-muted">
            <div
              className="h-2 rounded-full bg-primary"
              style={{
                width: `${Math.min(100, Math.round((progress.done / progress.total) * 100))}%`,
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
