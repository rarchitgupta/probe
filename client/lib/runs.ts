"use client"

import { useMutation, useQuery } from "@tanstack/react-query"

const API_URL = process.env.NEXT_PUBLIC_PROBE_API_URL ?? "http://127.0.0.1:8000"

export type RunStatus =
  "queued" | "running" | "passed" | "failed" | "blocked" | "error" | "cancelled"

export type CreateRunInput = {
  start_url: string
  goal: string
}

export type RunAccepted = {
  id: string
  status: RunStatus
}

export type RunResult = {
  task_id: string
  status: "passed" | "failed" | "blocked" | "error"
  start_url: string
  final_url: string | null
  http_status: number | null
  summary: string | null
  evidence: string[]
  diagnostics: unknown[]
  usage: Record<string, number | string>
  error: string | null
  artifact_directory: string
}

export type Run = {
  id: string
  title: string | null
  start_url: string
  goal: string
  status: RunStatus
  created_at: string
  started_at: string | null
  finished_at: string | null
  result: RunResult | null
  error: string | null
}

export type RunListItem = Pick<
  Run,
  | "id"
  | "title"
  | "start_url"
  | "goal"
  | "status"
  | "created_at"
  | "started_at"
  | "finished_at"
>

export type RunEvent = {
  id: number
  kind: "status" | "action" | "assertion"
  created_at: string
  status: RunStatus | null
  action: string | null
  element: string | null
  success: boolean | null
  message: string | null
}

async function responseJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`Probe API request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export async function createRun(input: CreateRunInput): Promise<RunAccepted> {
  return responseJson(
    await fetch(`${API_URL}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  )
}

export async function getRun(runId: string): Promise<Run> {
  return responseJson(await fetch(`${API_URL}/runs/${runId}`))
}

export async function getRuns(): Promise<RunListItem[]> {
  return responseJson(await fetch(`${API_URL}/runs`))
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  return responseJson(await fetch(`${API_URL}/runs/${runId}/events`))
}

export function useCreateRun() {
  return useMutation({ mutationFn: createRun })
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["runs", runId],
    queryFn: () => getRun(runId!),
    enabled: runId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === "queued" || status === "running" ? 2000 : false
    },
  })
}

export function useRuns() {
  return useQuery({ queryKey: ["runs"], queryFn: getRuns })
}

export function useRunEvents(runId: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["runs", runId, "events"],
    queryFn: () => getRunEvents(runId),
    refetchInterval: status === "queued" || status === "running" ? 1000 : false,
  })
}
