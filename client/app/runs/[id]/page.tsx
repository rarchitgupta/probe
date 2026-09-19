"use client"

import { use } from "react"

import { useRun, useRunEvents, useRunStream } from "@/lib/runs"
import { RunEvents } from "@/components/runs/run-events"
import { RunHeader } from "@/components/runs/run-header"
import { RunMetrics, RunOverview } from "@/components/runs/run-overview"
import { RunReplay } from "@/components/runs/run-replay"
import { RunResults } from "@/components/runs/run-results"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Skeleton } from "@/components/ui/skeleton"

export default function RunPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const runQuery = useRun(id)
  const eventsQuery = useRunEvents(id)
  useRunStream(id)

  if (runQuery.isPending) {
    return (
      <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 p-6 lg:p-8">
        <Skeleton className="h-8 w-72" />
        <Skeleton className="h-52 w-full" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-20" />
          ))}
        </div>
      </main>
    )
  }

  if (runQuery.isError) {
    return (
      <main className="p-8">Could not load run: {runQuery.error.message}</main>
    )
  }

  const run = runQuery.data
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 p-6 lg:p-8">
      <RunHeader run={run} />
      <RunOverview run={run} />
      <RunMetrics run={run} />

      <section className="grid items-stretch gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(20rem,2fr)]">
        <Card className="min-w-0 lg:h-[60dvh]">
          <CardHeader>
            <CardTitle>Events</CardTitle>
            <CardDescription>Live progress from this run</CardDescription>
          </CardHeader>
          <CardContent className="min-h-0 flex-1">
            <ScrollArea className="h-full">
              <div className="p-8">
                {eventsQuery.isPending && <p>Loading events...</p>}
                {eventsQuery.isError && <p>Could not load events.</p>}
                {eventsQuery.data && <RunEvents events={eventsQuery.data} />}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
        <RunResults run={run} />
      </section>
      <RunReplay run={run} />
    </main>
  )
}
