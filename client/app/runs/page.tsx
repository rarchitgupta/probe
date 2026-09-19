"use client"

import Link from "next/link"
import { PlusIcon } from "lucide-react"

import { RunListItem } from "@/components/runs/run-list-item"
import { Card, CardContent } from "@/components/ui/card"
import { buttonVariants } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useRuns } from "@/lib/runs"

export default function RunsPage() {
  const runs = useRuns()

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 p-6 lg:p-8">
      <header className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
          <p className="text-sm text-muted-foreground">
            Monitor recent QA tasks and review their results.
          </p>
        </div>
        <Link href="/" className={buttonVariants()}>
          <PlusIcon data-icon="inline-start" />
          New run
        </Link>
      </header>

      <section className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-sm font-medium">Recent runs</h2>
          {runs.data && (
            <p className="text-xs text-muted-foreground">
              Showing {runs.data.length}
            </p>
          )}
        </div>

        {runs.isPending && (
          <div className="space-y-3">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-36 w-full" />
            ))}
          </div>
        )}

        {runs.isError && (
          <Card>
            <CardContent className="text-sm text-destructive">
              Could not load runs: {runs.error.message}
            </CardContent>
          </Card>
        )}

        {runs.data?.length === 0 && (
          <Card>
            <CardContent className="py-8 text-center">
              <p className="font-medium">No runs yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Submit your first QA task to see it here.
              </p>
            </CardContent>
          </Card>
        )}

        <div className="space-y-3">
          {runs.data?.map((run) => (
            <RunListItem key={run.id} run={run} />
          ))}
        </div>
      </section>
    </main>
  )
}
