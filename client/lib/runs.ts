"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

const API_URL = process.env.NEXT_PUBLIC_PROBE_API_URL ?? "http://127.0.0.1:8000"

export type RunStatus =
  "queued" | "running" | "passed" | "failed" | "blocked" | "error" | "cancelled"

export type CreateRunInput = {
  start_url: string
  goal: string
}

export type RunUsage = {
  input_tokens: number | null
  output_tokens: number | null
  cache_read_tokens: number | null
  requests: number | null
  cost: string | null
}

export type RunResult = {
  final_url: string | null
  http_status: number | null
  summary: string | null
  evidence: string[]
  usage: RunUsage
}

export type RunStats = {
  duration_ms: number | null
  action_count: number
  assertion_count: number
  failed_action_count: number
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
  stats: RunStats
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

export async function createRun(input: CreateRunInput): Promise<Run> {
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
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: createRun,
    onSuccess: (run) => {
      queryClient.setQueryData(["runs", run.id], run)
      void queryClient.invalidateQueries({ queryKey: ["runs"], exact: true })
    },
  })
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
  return useQuery({
    queryKey: ["runs"],
    queryFn: getRuns,
    refetchInterval: (query) =>
      query.state.data?.some(
        (run) => run.status === "queued" || run.status === "running"
      )
        ? 2000
        : false,
  })
}

export function useRunEvents(runId: string, status?: RunStatus) {
  return useQuery({
    queryKey: ["runs", runId, "events"],
    queryFn: () => getRunEvents(runId),
    refetchInterval: status === "queued" || status === "running" ? 1000 : false,
  })
}
