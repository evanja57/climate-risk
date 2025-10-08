"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useToast } from "@/hooks/use-toast"
import { Toaster } from "@/components/ui/toaster"
import { JsonViewer } from "@/components/JsonViewer"
import { MarkdownView } from "@/components/MarkdownView"
import { ReportCards } from "@/components/ReportCards"
import { getLatestReport, getLatestEvidence, type CreateReportResponse } from "@/lib/api"
import { slugify } from "@/lib/slugify"
import { Loader2, FileJson, FileText, FolderOpen } from "lucide-react"
import { useEventSource } from "@/lib/useEventSource"
import { ProgressPanel, type ProgressState } from "@/components/ProgressPanel"

const STORAGE_KEY = "transition-risk-last-company"

const createInitialProgress = (): ProgressState => ({
  current: "idle",
  stages: {
    scope: "idle",
    aggregate_sources: "idle",
    rank_filter: "idle",
    convert_docs: "idle",
    synthesize: "idle",
    model_risk: "idle",
    finalize: "idle",
  },
  progress: undefined,
  ticker: [],
  artifacts: [],
  headline: undefined,
  note: undefined,
})

export default function Home() {
  const { toast } = useToast()
  const [company, setCompany] = useState("")
  const [perQ, setPerQ] = useState(2)
  const [pdfCap, setPdfCap] = useState(5)
  const [reportData, setReportData] = useState<CreateReportResponse | null>(null)
  const [evidenceText, setEvidenceText] = useState("")
  const [validationError, setValidationError] = useState("")
  const previousReportRef = useRef<CreateReportResponse | null>(null)
  const previousEvidenceRef = useRef("")
  const runningCompanyRef = useRef<string | null>(null)
  const hasReceivedDoneRef = useRef(false)
  const [hasCompletedReport, setHasCompletedReport] = useState(false)
  const [progressState, setProgressState] = useState<ProgressState>(() => createInitialProgress())
  const progressStateRef = useRef<ProgressState>(progressState)
  const commitProgressState = useCallback(
    (updater: ProgressState | ((prev: ProgressState) => ProgressState)) => {
      setProgressState((prev) => {
        const next = typeof updater === "function" ? (updater as (p: ProgressState) => ProgressState)(prev) : updater
        progressStateRef.current = next
        return next
      })
    },
    [setProgressState],
  )
  const [streamUrl, setStreamUrl] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)
  const [isFetchingArtifacts, setIsFetchingArtifacts] = useState(false)

  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) setCompany(saved)
  }, [])

  const stashCurrentResults = useCallback(() => {
    previousReportRef.current = reportData
    previousEvidenceRef.current = evidenceText
  }, [evidenceText, reportData])

  const clearResultsForNewRun = useCallback(() => {
    stashCurrentResults()
    setReportData(null)
    setEvidenceText("")
    setHasCompletedReport(false)
    const initial = createInitialProgress()
    commitProgressState(initial)
    hasReceivedDoneRef.current = false
  }, [commitProgressState, stashCurrentResults])

  const restorePreviousResults = useCallback(() => {
    setReportData(previousReportRef.current)
    setEvidenceText(previousEvidenceRef.current)
    setHasCompletedReport(Boolean(previousReportRef.current))
  }, [setEvidenceText, setHasCompletedReport, setReportData])

  const fetchLatestArtifacts = useCallback(async (targetCompany: string) => {
    const slug = slugify(targetCompany)
    const [report, evidence] = await Promise.all([
      getLatestReport(slug),
      getLatestEvidence(slug).catch(() => ({ text: "" })),
    ])

    return {
      report,
      evidenceText: evidence.text ?? "",
    }
  }, [])

  const handleRunReport = () => {
    if (!company.trim()) {
      setValidationError("Company name is required")
      return
    }

    const targetCompany = company.trim()
    runningCompanyRef.current = targetCompany

    setValidationError("")
    setStreamError(null)
    clearResultsForNewRun()
    setIsStreaming(true)

    const payload = encodeURIComponent(
      JSON.stringify({ company: targetCompany, per_q: perQ, pdf_cap: pdfCap }),
    )
    const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000"
    setStreamUrl(`${base}/api/report/stream?payload=${payload}`)
  }

  const handleCancelRun = useCallback(() => {
    setStreamUrl(null)
    setIsStreaming(false)
    setIsFetchingArtifacts(false)
    setStreamError(null)
    commitProgressState(createInitialProgress())
    restorePreviousResults()
    runningCompanyRef.current = null
    hasReceivedDoneRef.current = false

    toast({
      title: "Generation cancelled",
      description: "Stopped the current report generation.",
    })
  }, [commitProgressState, restorePreviousResults, toast])

  const handleLoadLatest = async () => {
    if (!company.trim()) {
      setValidationError("Company name is required")
      return
    }

    const targetCompany = company.trim()
    runningCompanyRef.current = targetCompany

    setValidationError("")
    setStreamError(null)
    setStreamUrl(null)
    setIsStreaming(false)
    clearResultsForNewRun()
    setIsFetchingArtifacts(true)

    try {
      const { report, evidenceText: latestEvidence } = await fetchLatestArtifacts(targetCompany)

      setReportData({
        company: targetCompany,
        run_dir: "",
        report,
        artifacts: {
          report_json: "",
          report_raw: "",
          evidence_md: "",
        },
      })
      setEvidenceText(latestEvidence)
      setHasCompletedReport(true)
      localStorage.setItem(STORAGE_KEY, targetCompany)

      toast({
        title: "Report loaded",
        description: `Successfully loaded latest report for ${targetCompany}`,
      })
    } catch (error) {
      restorePreviousResults()
      toast({
        title: "Error loading report",
        description: error instanceof Error ? error.message : "Unknown error",
        variant: "destructive",
      })
    } finally {
      setIsFetchingArtifacts(false)
      runningCompanyRef.current = null
    }
  }

  const handleStreamMessage = useCallback(
    (event: any) => {
      if (!event || !event.type) return

      setStreamError(null)
      commitProgressState((prev) => {
        const next: ProgressState = {
          ...prev,
          stages: { ...prev.stages },
          ticker: [...prev.ticker],
          artifacts: [...prev.artifacts],
        }

        switch (event.type) {
          case "stage": {
            const stageId = event.id as keyof ProgressState["stages"]
            if (stageId && stageId in next.stages) {
              const state = event.state === "end" ? "end" : "start"
              next.stages[stageId] = state
              if (state === "start") {
                next.current = stageId
              } else if (state === "end" && next.current === stageId) {
                next.current = "idle"
              }
            }
            if (event.headline) next.headline = event.headline
            if (typeof event.note === "string") next.note = event.note
            return next
          }
          case "progress": {
            if (event.id === "convert_docs") {
              next.current = "convert_docs"
              next.progress = {
                done: Number(event.done) || 0,
                total: Number(event.total) || 0,
              }
            }
            return next
          }
          case "artifact": {
            if (event.name && event.url) {
              const exists = next.artifacts.some(
                (artifact) => artifact.name === event.name && artifact.url === event.url,
              )
              if (!exists) {
                next.artifacts = [...next.artifacts, { name: event.name, url: event.url }]
              }
            }
            return next
          }
          case "ticker": {
            if (typeof event.message === "string" && event.message.trim()) {
              const recent = next.ticker.slice(-9)
              recent.push(event.message.trim())
              next.ticker = recent
            }
            return next
          }
          case "error": {
            next.current = "error"
            return next
          }
          case "done": {
            hasReceivedDoneRef.current = true
            next.current = "done"
            return next
          }
          default:
            return prev
        }
      })
      if (event.type === "error") {
        const message =
          typeof event.message === "string" && event.message.trim()
            ? event.message.trim()
            : "Pipeline encountered an unexpected error."
        setStreamError(message)
        setStreamUrl(null)
        setIsStreaming(false)
        setIsFetchingArtifacts(false)
        setReportData(previousReportRef.current)
        setEvidenceText(previousEvidenceRef.current)
        setHasCompletedReport(Boolean(previousReportRef.current))
        toast({
          title: "Pipeline error",
          description: message,
          variant: "destructive",
        })
      }
    },
    [commitProgressState, toast],
  )

  const handleStreamError = useCallback(
    (_event: Event) => {
      if (hasReceivedDoneRef.current) {
        return
      }

      const targetCompany = runningCompanyRef.current
      const finalizeCompleted = progressStateRef.current.stages.finalize === "end"

      setStreamUrl(null)
      setIsStreaming(false)

      if (targetCompany) {
        setStreamError(null)
        setIsFetchingArtifacts(true)

        const recover = async () => {
          try {
            const { report, evidenceText: latestEvidence } = await fetchLatestArtifacts(targetCompany)

            setReportData({
              company: targetCompany,
              run_dir: "",
              report,
              artifacts: {
                report_json: "",
                report_raw: "",
                evidence_md: "",
              },
            })
            setEvidenceText(latestEvidence)
            setHasCompletedReport(true)
            localStorage.setItem(STORAGE_KEY, targetCompany)

            commitProgressState((prev) => ({ ...prev, current: "done" }))

            hasReceivedDoneRef.current = true
            setStreamError(null)

            toast({
              title: "Report ready",
              description: finalizeCompleted
                ? `Report completed for ${targetCompany}. The stream closed early so we fetched the latest results automatically.`
                : `Report completed for ${targetCompany}. The streaming connection dropped, but we recovered the output automatically.`,
            })
          } catch (error) {
            const description =
              error instanceof Error ? error.message : "Lost connection while generating the report."
            setStreamError("Streaming connection interrupted")
            commitProgressState((prev) => ({ ...prev, current: "error" }))
            restorePreviousResults()
            toast({
              title: "Streaming error",
              description,
              variant: "destructive",
            })
          } finally {
            setIsFetchingArtifacts(false)
            runningCompanyRef.current = null
          }
        }

        void recover()
        return
      }

      setStreamError("Streaming connection interrupted")
      setIsFetchingArtifacts(false)
      commitProgressState((prev) => ({ ...prev, current: "error" }))
      restorePreviousResults()
      toast({
        title: "Streaming error",
        description: "Lost connection while generating the report.",
        variant: "destructive",
      })
      runningCompanyRef.current = null
    },
    [commitProgressState, fetchLatestArtifacts, restorePreviousResults, toast],
  )

  useEventSource(streamUrl, handleStreamMessage, handleStreamError)

  useEffect(() => {
    if (!isStreaming || progressState.current !== "done") {
      return
    }

    const targetCompany = runningCompanyRef.current
    if (!targetCompany) {
      setIsStreaming(false)
      return
    }

    setStreamUrl(null)
    setIsFetchingArtifacts(true)

    const loadGeneratedArtifacts = async () => {
      try {
        const { report, evidenceText: latestEvidence } = await fetchLatestArtifacts(targetCompany)

        setReportData({
          company: targetCompany,
          run_dir: "",
          report,
          artifacts: {
            report_json: "",
            report_raw: "",
            evidence_md: "",
          },
        })
        setEvidenceText(latestEvidence)
        setHasCompletedReport(true)
        localStorage.setItem(STORAGE_KEY, targetCompany)

        toast({
          title: "Report generated",
          description: `Successfully generated report for ${targetCompany}`,
        })
      } catch (error) {
        restorePreviousResults()
        toast({
          title: "Error loading results",
          description: error instanceof Error ? error.message : "Unknown error",
          variant: "destructive",
        })
      } finally {
        setIsStreaming(false)
        setIsFetchingArtifacts(false)
        runningCompanyRef.current = null
      }
    }

    void loadGeneratedArtifacts()
  }, [fetchLatestArtifacts, isStreaming, progressState.current, restorePreviousResults, toast])

  const isBusy = isStreaming || isFetchingArtifacts
  const shouldShowProgress =
    isStreaming || (progressState.current !== "idle" && progressState.current !== "done")

  const getSummaryChips = () => {
    if (!reportData?.report) return null

    const chips: { label: string; value: string }[] = []

    if (reportData.report.company?.company_name) {
      chips.push({
        label: "Company",
        value: reportData.report.company.company_name,
      })
    }

    if (reportData.report.risk_assessment?.overall_transition_risk_rating) {
      chips.push({
        label: "Risk Rating",
        value: reportData.report.risk_assessment.overall_transition_risk_rating,
      })
    }

    if (
      reportData.report.risk_assessment?.risk_matrix &&
      Array.isArray(reportData.report.risk_assessment.risk_matrix)
    ) {
      chips.push({
        label: "Risk Items",
        value: String(reportData.report.risk_assessment.risk_matrix.length),
      })
    }

    return chips.length > 0 ? (
      <div className="flex flex-wrap gap-2 mb-4">
        {chips.map((chip, idx) => (
          <div
            key={idx}
            className="inline-flex items-center gap-2 bg-secondary text-secondary-foreground px-3 py-1 rounded-full text-sm"
          >
            <span className="font-medium">{chip.label}:</span>
            <span>{chip.value}</span>
          </div>
        ))}
      </div>
    ) : null
  }

  return (
    <div className="min-h-screen bg-white">
      <Toaster />

      <header className="sticky top-0 z-10 bg-white border-b border-border shadow-sm">
        <div className="container mx-auto px-4 py-6">
          <h1 className="text-3xl font-bold text-foreground">Transition Risk Scout</h1>
          <p className="text-sm text-muted-foreground mt-1"></p>
        </div>
      </header>

      <main className="container mx-auto px-4 py-8 space-y-8">
        <Card className="shadow-lg rounded-2xl">
          <CardHeader>
            <CardTitle>Generate Report</CardTitle>
            <CardDescription>
              Enter a company name to generate a transition risk report or load the latest one
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="company">
                  Company name <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="company"
                  type="text"
                  placeholder="e.g., McDonalds"
                  value={company}
                  onChange={(e) => {
                    setCompany(e.target.value)
                    setValidationError("")
                  }}
                  disabled={isBusy}
                  aria-required="true"
                  aria-invalid={!!validationError}
                  aria-describedby={validationError ? "company-error" : undefined}
                />
                {validationError && (
                  <p id="company-error" className="text-sm text-destructive">
                    {validationError}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="per-q">Max results/query (per_q)</Label>
                <Input
                  id="per-q"
                  type="number"
                  min="1"
                  value={perQ}
                  onChange={(e) => setPerQ(Number(e.target.value))}
                  disabled={isBusy}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="pdf-cap">PDF cap (pdf_cap)</Label>
                <Input
                  id="pdf-cap"
                  type="number"
                  min="1"
                  value={pdfCap}
                  onChange={(e) => setPdfCap(Number(e.target.value))}
                  disabled={isBusy}
                />
              </div>
            </div>

            <div className="flex gap-3">
              <Button onClick={handleRunReport} disabled={isBusy} className="flex-1 md:flex-none">
                {isStreaming && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isStreaming ? "Streaming…" : "Run report"}
              </Button>
              {isBusy && (
                <Button
                  variant="destructive"
                  onClick={handleCancelRun}
                  className="flex-1 md:flex-none"
                >
                  Cancel
                </Button>
              )}
              <Button
                variant="outline"
                onClick={handleLoadLatest}
                disabled={isBusy}
                className="flex-1 md:flex-none bg-transparent"
              >
                {isFetchingArtifacts && !isStreaming && (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                )}
                Load latest
              </Button>
            </div>
          </CardContent>
        </Card>

        {shouldShowProgress && (
          <Card className="shadow-lg rounded-2xl">
            <CardContent className="p-6">
              <ProgressPanel state={progressState} />
              {streamError && (
                <p className="mt-4 text-sm text-destructive">{streamError}</p>
              )}
            </CardContent>
          </Card>
        )}

        {isFetchingArtifacts ? (
          <Card className="shadow-lg rounded-2xl">
            <CardContent className="py-12 flex flex-col items-center gap-3 text-muted-foreground">
              <Loader2 className="h-10 w-10 animate-spin" />
              <p className="text-sm font-medium">Preparing artifacts…</p>
            </CardContent>
          </Card>
        ) : hasCompletedReport ? (
          <Card className="shadow-lg rounded-2xl">
            <CardContent className="pt-6">
              <Tabs defaultValue="report" className="w-full">
                <TabsList className="grid w-full grid-cols-3 mb-6">
                  <TabsTrigger value="report">Report</TabsTrigger>
                  <TabsTrigger value="raw-json">Raw JSON</TabsTrigger>
                  <TabsTrigger value="artifacts">Artifacts</TabsTrigger>
                </TabsList>

                <TabsContent value="report" className="space-y-4">
                  {reportData?.report ? (
                    <>
                      {getSummaryChips()}
                      <ReportCards data={reportData.report} />
                    </>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <FileJson className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No report yet</p>
                      <p className="text-sm mt-2">Generate a report or load the latest one to see results</p>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="raw-json" className="space-y-4">
                  {reportData?.report ? (
                    <JsonViewer data={reportData.report} filename="report.json" />
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <FileJson className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No report yet</p>
                      <p className="text-sm mt-2">Generate a report or load the latest one to see raw JSON</p>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="artifacts">
                  {reportData?.artifacts || evidenceText ? (
                    <div className="space-y-6">
                      {reportData?.artifacts && (
                        <div>
                          <h3 className="text-lg font-semibold mb-3">Files</h3>
                          <div className="grid gap-4 md:grid-cols-3">
                            {[
                              {
                                name: "report.json",
                                path: reportData.artifacts.report_json,
                                icon: FileJson,
                                downloadable: true,
                              },
                              {
                                name: "report_raw.txt",
                                path: reportData.artifacts.report_raw,
                                icon: FileText,
                                downloadable: false,
                              },
                              {
                                name: "evidence.md",
                                path: reportData.artifacts.evidence_md,
                                icon: FileText,
                                downloadable: false,
                              },
                            ].map((artifact) => (
                              <Card key={artifact.name} className="shadow">
                                <CardHeader>
                                  <CardTitle className="text-base flex items-center gap-2">
                                    <artifact.icon className="h-5 w-5" />
                                    {artifact.name}
                                  </CardTitle>
                                </CardHeader>
                                <CardContent>
                                  {artifact.downloadable ? (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="bg-transparent"
                                      onClick={() => {
                                        const blob = new Blob(
                                          [JSON.stringify(reportData.report, null, 2)],
                                          {
                                            type: "application/json",
                                          }
                                        )
                                        const url = URL.createObjectURL(blob)
                                        const a = document.createElement("a")
                                        a.href = url
                                        a.download = artifact.name
                                        a.click()
                                        URL.revokeObjectURL(url)
                                      }}
                                    >
                                      Download
                                    </Button>
                                  ) : (
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="bg-transparent"
                                      disabled
                                      title="Download not exposed"
                                    >
                                      Download
                                    </Button>
                                  )}
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        </div>
                      )}

                      {evidenceText && (
                        <div>
                          <h3 className="text-lg font-semibold mb-3">Evidence Documentation</h3>
                          <Card className="shadow">
                            <CardContent className="pt-6">
                              <MarkdownView markdown={evidenceText} />
                            </CardContent>
                          </Card>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <FolderOpen className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>No artifacts yet</p>
                      <p className="text-sm mt-2">Generate a report to see artifact paths and evidence</p>
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        ) : null}
      </main>
    </div>
  )
}
