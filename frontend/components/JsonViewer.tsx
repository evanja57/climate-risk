"use client"

import { useState } from "react"
import { Button } from "@/components/ui/button"
import { ChevronDown, ChevronRight, Copy, Download } from "lucide-react"
import { useToast } from "@/hooks/use-toast"
import type { JSX } from "react/jsx-runtime" // Import JSX to fix the undeclared variable error

interface JsonViewerProps {
  data: any
  filename?: string
}

export function JsonViewer({ data, filename = "report.json" }: JsonViewerProps) {
  const { toast } = useToast()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggleExpand = (path: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      return next
    })
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(JSON.stringify(data, null, 2))
    toast({
      title: "Copied to clipboard",
      description: "JSON data copied successfully",
    })
  }

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: "application/json",
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const renderValue = (value: any, path: string, depth: number): JSX.Element => {
    if (value === null) {
      return <span className="text-muted-foreground">null</span>
    }

    if (typeof value === "boolean") {
      return <span className="text-blue-600">{value.toString()}</span>
    }

    if (typeof value === "number") {
      return <span className="text-green-600">{value}</span>
    }

    if (typeof value === "string") {
      return <span className="text-orange-600">&quot;{value}&quot;</span>
    }

    if (Array.isArray(value)) {
      const isExpanded = expanded.has(path)
      return (
        <div>
          <button
            onClick={() => toggleExpand(path)}
            className="inline-flex items-center gap-1 hover:bg-muted rounded px-1"
            aria-label={isExpanded ? "Collapse array" : "Expand array"}
          >
            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <span className="text-muted-foreground">
              [{value.length} {value.length === 1 ? "item" : "items"}]
            </span>
          </button>
          {isExpanded && (
            <div className="ml-6 border-l-2 border-border pl-4 mt-1">
              {value.map((item, idx) => (
                <div key={idx} className="py-1">
                  <span className="text-muted-foreground">{idx}: </span>
                  {renderValue(item, `${path}[${idx}]`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    if (typeof value === "object") {
      const isExpanded = expanded.has(path)
      const keys = Object.keys(value)
      return (
        <div>
          <button
            onClick={() => toggleExpand(path)}
            className="inline-flex items-center gap-1 hover:bg-muted rounded px-1"
            aria-label={isExpanded ? "Collapse object" : "Expand object"}
          >
            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <span className="text-muted-foreground">
              {"{"}
              {keys.length} {keys.length === 1 ? "key" : "keys"}
              {"}"}
            </span>
          </button>
          {isExpanded && (
            <div className="ml-6 border-l-2 border-border pl-4 mt-1">
              {keys.map((key) => (
                <div key={key} className="py-1">
                  <span className="font-medium">{key}: </span>
                  {renderValue(value[key], `${path}.${key}`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    return <span>{String(value)}</span>
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <Button variant="outline" size="sm" onClick={copyToClipboard} aria-label="Copy JSON to clipboard">
          <Copy className="h-4 w-4 mr-2" />
          Copy JSON
        </Button>
        <Button variant="outline" size="sm" onClick={downloadJson} aria-label="Download JSON file">
          <Download className="h-4 w-4 mr-2" />
          Download JSON
        </Button>
      </div>
      <div className="bg-muted/30 rounded-xl p-6 font-mono text-sm overflow-auto max-h-[600px]">
        {renderValue(data, "root", 0)}
      </div>
    </div>
  )
}
