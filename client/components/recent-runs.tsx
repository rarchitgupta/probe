"use client"

import Link from "next/link"
import { ArrowRightIcon, LinkIcon } from "lucide-react"

import { StatusBadge } from "@/components/status-badge"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useRuns } from "@/lib/runs"

export function RecentRuns() {
  const runs = useRuns()
  const recent = runs.data?.slice(0, 4)

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
        <CardDescription>Your latest QA tasks</CardDescription>
        <CardAction>
          <Link
            href="/runs"
            className="inline-flex items-center gap-1 text-xs text-primary underline-offset-4 hover:underline"
          >
            View all
            <ArrowRightIcon className="size-3.5" />
          </Link>
        </CardAction>
      </CardHeader>
      <CardContent>
        {runs.isPending && (
          <div className="space-y-3">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-16 w-full" />
            ))}
          </div>
        )}

        {runs.isError && (
          <p className="text-xs text-destructive">
            Could not load recent runs.
          </p>
        )}

        {recent?.length === 0 && (
          <div className="py-8 text-center">
            <p className="text-sm font-medium">No runs yet</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Your first task will appear here.
            </p>
          </div>
        )}

        {recent && recent.length > 0 && (
          <div className="divide-y border-y">
            {recent.map((run) => (
              <Link
                key={run.id}
                href={`/runs/${run.id}`}
                className="flex items-center justify-between gap-3 px-1 py-3 transition-colors hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
              >
                <div className="min-w-0 space-y-1">
                  <p className="truncate text-sm font-medium">
                    {run.title ?? "Preparing run…"}
                  </p>
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <LinkIcon className="size-3.5 shrink-0" />
                    <span className="truncate">
                      {new URL(run.start_url).hostname}
                    </span>
                  </p>
                </div>
                <StatusBadge status={run.status} />
              </Link>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
