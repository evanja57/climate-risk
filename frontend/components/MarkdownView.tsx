"use client"

import { useState, useMemo } from "react"
import { Input } from "@/components/ui/input"
import { Search } from "lucide-react"
import type { JSX } from "react/jsx-runtime" // Import JSX to declare it

interface MarkdownViewProps {
  markdown: string
}

export function MarkdownView({ markdown }: MarkdownViewProps) {
  const [filter, setFilter] = useState("")

  // Simple markdown parser for headings, lists, code blocks, and inline links
  const renderMarkdown = (text: string) => {
    const lines = text.split("\n")
    const elements: JSX.Element[] = []
    let inCodeBlock = false
    let codeLines: string[] = []
    let codeLanguage = ""
    let listItems: string[] = []
    let inList = false

    const flushList = () => {
      if (listItems.length > 0) {
        elements.push(
          <ul key={`list-${elements.length}`} className="list-disc list-inside space-y-1 my-4">
            {listItems.map((item, idx) => (
              <li key={idx} className="leading-relaxed">
                {parseInline(item)}
              </li>
            ))}
          </ul>,
        )
        listItems = []
        inList = false
      }
    }

    const parseInline = (text: string) => {
      // Parse inline links [text](url)
      const parts: (string | JSX.Element)[] = []
      let remaining = text
      let key = 0

      while (remaining) {
        const linkMatch = remaining.match(/\[([^\]]+)\]$$([^)]+)$$/)
        if (linkMatch) {
          const before = remaining.slice(0, linkMatch.index)
          if (before) parts.push(before)
          parts.push(
            <a
              key={key++}
              href={linkMatch[2]}
              className="text-primary underline hover:text-primary/80"
              target="_blank"
              rel="noopener noreferrer"
            >
              {linkMatch[1]}
            </a>,
          )
          remaining = remaining.slice(linkMatch.index! + linkMatch[0].length)
        } else {
          parts.push(remaining)
          break
        }
      }

      return parts
    }

    lines.forEach((line, idx) => {
      // Code blocks
      if (line.startsWith("```")) {
        if (inCodeBlock) {
          elements.push(
            <pre key={`code-${elements.length}`} className="bg-muted rounded-lg p-4 overflow-x-auto my-4">
              <code className="font-mono text-sm">{codeLines.join("\n")}</code>
            </pre>,
          )
          codeLines = []
          inCodeBlock = false
          codeLanguage = ""
        } else {
          flushList()
          inCodeBlock = true
          codeLanguage = line.slice(3).trim()
        }
        return
      }

      if (inCodeBlock) {
        codeLines.push(line)
        return
      }

      // Headings
      if (line.startsWith("# ")) {
        flushList()
        const text = line.slice(2)
        if (!filter || text.toLowerCase().includes(filter.toLowerCase())) {
          elements.push(
            <h1 key={idx} className="text-3xl font-bold mt-8 mb-4">
              {text}
            </h1>,
          )
        }
        return
      }

      if (line.startsWith("## ")) {
        flushList()
        const text = line.slice(3)
        if (!filter || text.toLowerCase().includes(filter.toLowerCase())) {
          elements.push(
            <h2 key={idx} className="text-2xl font-semibold mt-6 mb-3">
              {text}
            </h2>,
          )
        }
        return
      }

      if (line.startsWith("### ")) {
        flushList()
        const text = line.slice(4)
        if (!filter || text.toLowerCase().includes(filter.toLowerCase())) {
          elements.push(
            <h3 key={idx} className="text-xl font-semibold mt-4 mb-2">
              {text}
            </h3>,
          )
        }
        return
      }

      // List items
      if (line.match(/^[\s]*[-*]\s/)) {
        if (!inList) inList = true
        listItems.push(line.replace(/^[\s]*[-*]\s/, ""))
        return
      }

      // Flush list if we hit non-list content
      if (inList && line.trim()) {
        flushList()
      }

      // Paragraphs
      if (line.trim()) {
        elements.push(
          <p key={idx} className="leading-relaxed my-3">
            {parseInline(line)}
          </p>,
        )
      }
    })

    flushList()

    return elements
  }

  const filteredMarkdown = useMemo(() => {
    if (!filter) return markdown

    // Filter by sections that contain the search term in headings
    const lines = markdown.split("\n")
    const sections: string[] = []
    let currentSection: string[] = []
    let includeSection = false

    lines.forEach((line) => {
      if (line.match(/^#{1,3}\s/)) {
        if (includeSection && currentSection.length > 0) {
          sections.push(currentSection.join("\n"))
        }
        currentSection = [line]
        includeSection = line.toLowerCase().includes(filter.toLowerCase())
      } else {
        currentSection.push(line)
      }
    })

    if (includeSection && currentSection.length > 0) {
      sections.push(currentSection.join("\n"))
    }

    return sections.join("\n\n")
  }, [markdown, filter])

  return (
    <div className="space-y-4">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Filter by heading..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="pl-10"
          aria-label="Filter markdown by heading"
        />
      </div>
      <div className="prose prose-sm max-w-none">{renderMarkdown(filteredMarkdown)}</div>
    </div>
  )
}
