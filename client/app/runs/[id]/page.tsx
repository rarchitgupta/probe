"use client"

import { use } from "react"

import { useRun, useRunEvents } from "@/lib/runs"

function dateTime(value: string | null) {
  return value ? new Date(value).toLocaleString() : "—"
}

export default function RunPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)
  const runQuery = useRun(id)
  const eventsQuery = useRunEvents(id, runQuery.data?.status)

  if (runQuery.isPending) {
    return <main className="p-8">Loading run...</main>
  }

  if (runQuery.isError) {
    return (
      <main className="p-8">Could not load run: {runQuery.error.message}</main>
    )
  }

  const run = runQuery.data
  const error = run.error ?? run.result?.error

  return (
    <main className="flex flex-1 flex-col gap-6 p-8">
      <header>
        <h1 className="text-2xl font-semibold">
          {run.title ?? "Untitled run"}
        </h1>
        <p>Status: {run.status}</p>
      </header>

      <section>
        <h2 className="font-semibold">Task</h2>
        <p>Run ID: {run.id}</p>
        <p>
          Website: <a href={run.start_url}>{run.start_url}</a>
        </p>
        <p>Instructions: {run.goal}</p>
        <p>Created: {dateTime(run.created_at)}</p>
        <p>Started: {dateTime(run.started_at)}</p>
        <p>Finished: {dateTime(run.finished_at)}</p>
      </section>

      {run.result && (
        <section>
          <h2 className="font-semibold">Result</h2>
          <p>Summary: {run.result.summary ?? "—"}</p>
          <p>Final URL: {run.result.final_url ?? "—"}</p>
          <p>HTTP status: {run.result.http_status ?? "—"}</p>

          <h3 className="font-medium">Evidence</h3>
          {run.result.evidence.length ? (
            <ul>
              {run.result.evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p>—</p>
          )}

          <h3 className="font-medium">Usage</h3>
          <ul>
            {Object.entries(run.result.usage).map(([key, value]) => (
              <li key={key}>
                {key}: {value}
              </li>
            ))}
          </ul>
        </section>
      )}

      {error && (
        <section>
          <h2 className="font-semibold">Error</h2>
          <p>{error}</p>
        </section>
      )}

      <section>
        <h2 className="font-semibold">Events</h2>
        {eventsQuery.isPending && <p>Loading events...</p>}
        {eventsQuery.isError && <p>Could not load events.</p>}
        {eventsQuery.data?.map((event) => (
          <p key={event.id}>
            {new Date(event.created_at).toLocaleTimeString()} —{" "}
            {event.action ?? event.status}: {event.element ?? event.message}
          </p>
        ))}
      </section>
    </main>
  )
}
