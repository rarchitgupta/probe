import Link from "next/link"
import {
  CalendarClockIcon,
  ChevronRightIcon,
  LinkIcon,
  TimerIcon,
} from "lucide-react"

import { StatusBadge } from "@/components/status-badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { RunListItem as RunListItemType } from "@/lib/runs"

function duration(run: RunListItemType) {
  if (!run.started_at || !run.finished_at) return null
  const milliseconds =
    new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()
  return milliseconds < 1000
    ? `${milliseconds} ms`
    : `${(milliseconds / 1000).toFixed(2)} s`
}

export function RunListItem({ run }: { run: RunListItemType }) {
  const elapsed = duration(run)

  return (
    <Link
      href={`/runs/${run.id}`}
      className="group block focus-visible:outline-none"
    >
      <Card className="transition-colors group-focus-visible:ring-2 group-focus-visible:ring-ring/50 hover:bg-muted/30">
        <CardHeader className="grid-cols-[minmax(0,1fr)_auto]">
          <div className="min-w-0 space-y-1">
            <CardTitle className="truncate text-base">
              {run.title ?? "Preparing run…"}
            </CardTitle>
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <LinkIcon className="size-3.5 shrink-0" />
              <span className="truncate">
                {new URL(run.start_url).hostname}
              </span>
            </p>
          </div>
          <div className="flex items-center gap-3">
            <StatusBadge status={run.status} />
            <ChevronRightIcon className="size-4 text-muted-foreground" />
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="line-clamp-2 max-w-4xl text-sm leading-relaxed text-muted-foreground">
            {run.goal}
          </p>
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <CalendarClockIcon className="size-3.5" />
              {new Date(run.created_at).toLocaleString()}
            </span>
            {elapsed && (
              <span className="flex items-center gap-1.5">
                <TimerIcon className="size-3.5" />
                {elapsed}
              </span>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
