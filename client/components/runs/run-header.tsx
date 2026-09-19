"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeftIcon, CopyIcon, RotateCcwIcon, XIcon } from "lucide-react"
import { toast } from "sonner"

import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { runTitle, type Run, useCancelRun, useRerun } from "@/lib/runs"

export function RunHeader({ run }: { run: Run }) {
  const router = useRouter()
  const cancelRun = useCancelRun()
  const rerun = useRerun()
  const hostname = new URL(run.start_url).hostname
  const active = run.status === "queued" || run.status === "running"

  async function copyRunId() {
    try {
      await navigator.clipboard.writeText(run.id)
      toast.success("Run ID copied")
    } catch {
      toast.error("Could not copy run ID")
    }
  }

  function cancel() {
    cancelRun.mutate(run.id, {
      onSuccess: () => toast.success("Run cancelled"),
      onError: (error) =>
        toast.error("Could not cancel run", { description: error.message }),
    })
  }

  function runAgain() {
    rerun.mutate(run.id, {
      onSuccess: (nextRun) => {
        toast.success("Rerun queued")
        router.push(`/runs/${nextRun.id}`)
      },
      onError: (error) =>
        toast.error("Could not rerun task", { description: error.message }),
    })
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
            {runTitle(run)}
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
        <div className="flex items-center gap-2">
          {active ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={cancel}
              disabled={cancelRun.isPending}
            >
              <XIcon data-icon="inline-start" />
              {cancelRun.isPending ? "Cancelling…" : "Cancel"}
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={runAgain}
              disabled={rerun.isPending}
            >
              <RotateCcwIcon data-icon="inline-start" />
              {rerun.isPending ? "Queuing…" : "Rerun"}
            </Button>
          )}
          <StatusBadge status={run.status} />
        </div>
      </div>
    </header>
  )
}
