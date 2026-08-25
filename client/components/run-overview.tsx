import {
  CircleAlertIcon,
  Clock3Icon,
  ExternalLinkIcon,
  ListChecksIcon,
  MousePointerClickIcon,
} from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import type { Run } from "@/lib/runs"

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—"
}

function duration(milliseconds: number | null) {
  if (milliseconds === null) return "—"
  return milliseconds < 1000
    ? `${milliseconds} ms`
    : `${(milliseconds / 1000).toFixed(2)} s`
}

export function RunOverview({ run }: { run: Run }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Task</CardTitle>
        <CardDescription>What Probe was asked to verify</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="max-w-4xl text-sm leading-relaxed">{run.goal}</p>
        <a
          href={run.start_url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex max-w-full items-center gap-1.5 rounded-none bg-muted px-2 py-1 font-mono text-xs text-primary underline-offset-4 hover:underline"
        >
          <span className="truncate">{run.start_url}</span>
          <ExternalLinkIcon className="size-3.5 shrink-0" aria-hidden />
        </a>
        <Separator />
        <dl className="grid gap-3 text-xs sm:grid-cols-3">
          <div>
            <dt className="text-muted-foreground">Created</dt>
            <dd className="mt-1 font-medium">{dateTime(run.created_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Started</dt>
            <dd className="mt-1 font-medium">{dateTime(run.started_at)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Finished</dt>
            <dd className="mt-1 font-medium">{dateTime(run.finished_at)}</dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  )
}

const metrics = [
  { key: "duration", label: "Duration", icon: Clock3Icon },
  { key: "actions", label: "Browser actions", icon: MousePointerClickIcon },
  { key: "assertions", label: "Assertions", icon: ListChecksIcon },
  { key: "failures", label: "Failed actions", icon: CircleAlertIcon },
] as const

export function RunMetrics({ run }: { run: Run }) {
  const values = {
    duration: duration(run.stats.duration_ms),
    actions: run.stats.action_count,
    assertions: run.stats.assertion_count,
    failures: run.stats.failed_action_count,
  }

  return (
    <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map(({ key, label, icon: Icon }) => (
        <Card key={key} size="sm">
          <CardContent className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="mt-1 text-lg font-semibold tabular-nums">
                {values[key]}
              </p>
            </div>
            <Icon className="size-5 text-muted-foreground" aria-hidden />
          </CardContent>
        </Card>
      ))}
    </section>
  )
}
