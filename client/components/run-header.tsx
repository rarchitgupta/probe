"use client"

import Link from "next/link"
import { ArrowLeftIcon, CopyIcon } from "lucide-react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import type { Run } from "@/lib/runs"

export function RunHeader({ run }: { run: Run }) {
  const hostname = new URL(run.start_url).hostname

  async function copyRunId() {
    try {
      await navigator.clipboard.writeText(run.id)
      toast.success("Run ID copied")
    } catch {
      toast.error("Could not copy run ID")
    }
  }

  return (
    <header className="space-y-4">
      <Link
        href="/runs"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeftIcon className="size-4" />
        Runs
      </Link>

      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
        <div className="min-w-0 space-y-1">
          <h1 className="truncate text-2xl font-semibold tracking-tight">
            {run.title ?? "Preparing run…"}
          </h1>
          <p className="text-sm text-muted-foreground">{hostname}</p>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <span className="font-mono">{run.id}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              onClick={copyRunId}
              aria-label="Copy run ID"
              title="Copy run ID"
            >
              <CopyIcon />
            </Button>
          </div>
        </div>
        <StatusBadge status={run.status} />
      </div>
    </header>
  )
}
