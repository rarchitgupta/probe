"use client"

import Link from "next/link"
import {
  Ban,
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock3,
  LoaderCircle,
  OctagonX,
  type LucideIcon,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { type RunStatus, useRuns } from "@/lib/runs"

const statusBadges: Record<RunStatus, { icon: LucideIcon; className: string }> =
  {
    queued: { icon: Clock3, className: "bg-muted text-muted-foreground" },
    running: {
      icon: LoaderCircle,
      className:
        "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300",
    },
    passed: {
      icon: CircleCheck,
      className:
        "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300",
    },
    failed: {
      icon: CircleX,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    blocked: {
      icon: OctagonX,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    error: {
      icon: CircleAlert,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    cancelled: { icon: Ban, className: "bg-muted text-muted-foreground" },
  }

function StatusBadge({ status }: { status: RunStatus }) {
  const { icon: Icon, className } = statusBadges[status]

  return (
    <Badge variant="outline" className={`font-mono uppercase ${className}`}>
      <Icon data-icon="inline-start" />
      {status}
    </Badge>
  )
}

export default function RunsPage() {
  const runs = useRuns()

  return (
    <main className="flex flex-1 flex-col gap-2 p-8">
      {/* <h1 className="text-2xl font-semibold">Runs</h1> */}
      {runs.isPending && <p>Loading runs...</p>}
      {runs.isError && <p>Could not load runs: {runs.error.message}</p>}
      {runs.data?.length === 0 && <p>No runs yet.</p>}
      {runs.data?.map((run) => (
        <Card key={run.id} className="w-full">
          <CardHeader>
            <CardTitle>
              <Link href={`/runs/${run.id}`}>
                {run.title ?? "Untitled run"}
              </Link>
            </CardTitle>
            <CardAction>
              <StatusBadge status={run.status} />
            </CardAction>
          </CardHeader>
          <CardContent>
            <p>Website: {run.start_url}</p>
            <p>Created: {new Date(run.created_at).toLocaleString()}</p>
          </CardContent>
        </Card>
      ))}
    </main>
  )
}
