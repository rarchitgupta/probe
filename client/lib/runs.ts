"use client"

import { useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

const API_URL = process.env.NEXT_PUBLIC_PROBE_API_URL ?? "http://127.0.0.1:8000"

export type RunStatus =
  "queued" | "running" | "passed" | "failed" | "blocked" | "error" | "cancelled"

export type FailureCategory =
  | "model_timeout"
  | "model_error"
  | "execution_timeout"
  | "policy_violation"
  | "browser_error"
  | "assertion_failure"
  | "action_failure"
  | "infrastructure_error"

export type CreateRunInput = {
  start_url: string
  goal: string
  environment_id?: string
}

export type EnvironmentValue = { value: string } | { env: string }

export type TestEnvironment = {
  id: string
  name: string
  definition: {
    headers: Record<string, EnvironmentValue>
    cookies: Array<{
      name: string
      value: EnvironmentValue
      domain?: string | null
      path?: string
    }>
    secrets: Record<string, string>
  }
  viewport_width: number
  viewport_height: number
  created_at: string
}

export type CreateEnvironmentInput = Omit<TestEnvironment, "id" | "created_at">

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
  configuration: {
    model: string
    prompt_version: string
    model_config_version: string
  } | null
}

export type RunStats = {
  duration_ms: number | null
  action_count: number
  assertion_count: number
  failed_action_count: number
}

export type RunArtifact = {
  id: string
  kind: string
  content_type: string
  size_bytes: number
  created_at: string
  url: string
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
  artifacts: RunArtifact[]
  result: RunResult | null
  error: string | null
  failure_category: FailureCategory | null
  environment_id: string | null
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

export function runTitle(run: Pick<Run, "title" | "status">) {
  if (run.title) return run.title
  return run.status === "cancelled" ? "Cancelled run" : "Preparing run…"
}

export function artifactUrl(artifact: RunArtifact) {
  return new URL(artifact.url, API_URL).toString()
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

export async function getEnvironments(): Promise<TestEnvironment[]> {
  return responseJson(await fetch(`${API_URL}/environments`))
}

export async function createEnvironment(
  input: CreateEnvironmentInput
): Promise<TestEnvironment> {
  return responseJson(
    await fetch(`${API_URL}/environments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    })
  )
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  return responseJson(await fetch(`${API_URL}/runs/${runId}/events`))
}

export async function cancelRun(runId: string): Promise<Run> {
  return responseJson(
    await fetch(`${API_URL}/runs/${runId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "cancelled" }),
    })
  )
}

export async function rerunRun(runId: string): Promise<Run> {
  return responseJson(
    await fetch(`${API_URL}/runs/${runId}/reruns`, { method: "POST" })
  )
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
  })
}

export function useRuns() {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: ["runs"],
    queryFn: getRuns,
  })

  useEffect(() => {
    const source = new EventSource(`${API_URL}/runs/stream`)
    source.addEventListener("runs", (event) => {
      queryClient.setQueryData<RunListItem[]>(
        ["runs"],
        JSON.parse(event.data) as RunListItem[]
      )
    })
    return () => source.close()
  }, [queryClient])

  return query
}

export function useEnvironments() {
  return useQuery({ queryKey: ["environments"], queryFn: getEnvironments })
}

export function useCreateEnvironment() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createEnvironment,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["environments"] }),
  })
}

export function useRunEvents(runId: string) {
  return useQuery({
    queryKey: ["runs", runId, "events"],
    queryFn: () => getRunEvents(runId),
  })
}

export function useRunStream(runId: string) {
  const queryClient = useQueryClient()

  useEffect(() => {
    const source = new EventSource(`${API_URL}/runs/${runId}/stream`)

    source.addEventListener("run", (event) => {
      const run = JSON.parse(event.data) as Run
      queryClient.setQueryData(["runs", runId], run)
      queryClient.setQueryData<RunListItem[]>(["runs"], (runs) =>
        runs?.map((item) => (item.id === run.id ? { ...item, ...run } : item))
      )
      if (run.status !== "queued" && run.status !== "running") source.close()
    })
    source.addEventListener("progress", (event) => {
      const progress = JSON.parse(event.data) as RunEvent
      queryClient.setQueryData<RunEvent[]>(
        ["runs", runId, "events"],
        (events = []) =>
          events.some((item) => item.id === progress.id)
            ? events
            : [...events, progress]
      )
    })

    return () => source.close()
  }, [queryClient, runId])
}

export function useCancelRun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: cancelRun,
    onSuccess: (run) => {
      queryClient.setQueryData(["runs", run.id], run)
      void queryClient.invalidateQueries({ queryKey: ["runs"], exact: true })
      void queryClient.invalidateQueries({
        queryKey: ["runs", run.id, "events"],
      })
    },
  })
}

export function useRerun() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: rerunRun,
    onSuccess: (run) => {
      queryClient.setQueryData(["runs", run.id], run)
      void queryClient.invalidateQueries({ queryKey: ["runs"], exact: true })
    },
  })
}
