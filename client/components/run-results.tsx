import {
  CheckCircle2Icon,
  CircleAlertIcon,
  ExternalLinkIcon,
} from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import type { Run, RunUsage } from "@/lib/runs"
import { cn } from "@/lib/utils"

const usageLabels: Record<keyof RunUsage, string> = {
  input_tokens: "Input tokens",
  output_tokens: "Output tokens",
  cache_read_tokens: "Cached tokens",
  requests: "LLM requests",
  cost: "Cost",
}

function usageValue(key: keyof RunUsage, value: number | string) {
  if (key === "cost") return `$${Number(value).toFixed(6)}`
  return Number(value).toLocaleString()
}

export function RunResults({ run }: { run: Run }) {
  const result = run.result
  const passed = run.status === "passed"
  const OutcomeIcon = passed ? CheckCircle2Icon : CircleAlertIcon

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Results</CardTitle>
        <CardDescription>The final outcome and evidence</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {result ? (
          <>
            <div
              className={cn(
                "flex gap-3 border p-3",
                passed
                  ? "border-green-200 bg-green-50 text-green-800 dark:border-green-900 dark:bg-green-950/40 dark:text-green-300"
                  : "border-destructive/30 bg-destructive/5 text-destructive"
              )}
            >
              <OutcomeIcon className="mt-0.5 size-5 shrink-0" />
              <div>
                <p className="font-medium">
                  {passed ? "Run passed" : `Run ${run.status}`}
                </p>
                <p className="mt-1 text-xs leading-relaxed">
                  {result.summary ?? "The requested checks completed."}
                </p>
              </div>
            </div>

            <section className="space-y-2">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Destination
              </h3>
              <div className="flex flex-wrap items-center gap-2">
                {result.final_url ? (
                  <a
                    href={result.final_url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex min-w-0 items-center gap-1.5 text-sm text-primary underline-offset-4 hover:underline"
                  >
                    <span className="truncate">{result.final_url}</span>
                    <ExternalLinkIcon className="size-3.5 shrink-0" />
                  </a>
                ) : (
                  <span className="text-sm text-muted-foreground">—</span>
                )}
                {result.http_status !== null && (
                  <Badge variant="outline" className="font-mono">
                    HTTP {result.http_status}
                  </Badge>
                )}
              </div>
            </section>

            <Separator />

            <section className="space-y-3">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Evidence
              </h3>
              {result.evidence.length ? (
                <ul className="space-y-2">
                  {result.evidence.map((item) => (
                    <li
                      key={item}
                      className="flex gap-2 text-xs leading-relaxed"
                    >
                      <CheckCircle2Icon className="mt-0.5 size-4 shrink-0 text-green-600" />
                      <span className="break-words">{item}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-xs text-muted-foreground">
                  No evidence recorded.
                </p>
              )}
            </section>

            <Separator />

            <section className="space-y-3">
              <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Execution details
              </h3>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
                {Object.entries(result.usage).map(([key, value]) =>
                  value === null ? null : (
                    <div key={key}>
                      <dt className="text-xs text-muted-foreground">
                        {usageLabels[key as keyof RunUsage]}
                      </dt>
                      <dd className="mt-1 font-mono text-xs font-medium">
                        {usageValue(key as keyof RunUsage, value)}
                      </dd>
                    </div>
                  )
                )}
              </dl>
            </section>
          </>
        ) : run.error ? (
          <div className="flex gap-3 border border-destructive/30 bg-destructive/5 p-3 text-destructive">
            <CircleAlertIcon className="mt-0.5 size-5 shrink-0" />
            <div>
              <p className="font-medium">Run failed</p>
              <p className="mt-1 text-xs leading-relaxed">{run.error}</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3" aria-label="Waiting for results">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
