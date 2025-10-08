const BASE = process.env.NEXT_PUBLIC_API_BASE!

export type CreateReportBody = {
  company: string
  per_q?: number
  pdf_cap?: number
}

type SourcesMap = Record<string, { url: string; label?: string }>

export type CreateReportResponse = {
  company: string
  run_dir: string
  report: { sources?: SourcesMap; [k: string]: any }
  artifacts: {
    report_json: string
    report_raw: string
    evidence_md: string
  }
}

export type EvidenceResponse = {
  text: string
}

export async function createReport(body: CreateReportBody): Promise<CreateReportResponse> {
  const r = await fetch(`${BASE}/api/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const error = await r.json().catch(() => ({}))
    throw new Error(error.detail ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function getLatestReport(slug: string): Promise<any> {
  const r = await fetch(`${BASE}/api/runs/${slug}/latest/report.json`, {
    cache: "no-store",
  })
  if (!r.ok) {
    const error = await r.json().catch(() => ({}))
    throw new Error(error.detail ?? `HTTP ${r.status}`)
  }
  return r.json()
}

export async function getLatestEvidence(slug: string): Promise<EvidenceResponse> {
  const r = await fetch(`${BASE}/api/runs/${slug}/latest/evidence.md`, {
    cache: "no-store",
  })
  if (!r.ok) {
    const error = await r.json().catch(() => ({}))
    throw new Error(error.detail ?? `HTTP ${r.status}`)
  }
  return r.json()
}
