import { CheckIcon, ChevronRightIcon, CircleDotIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Spinner } from "@/components/ui/spinner"
import type { RunEvent } from "@/lib/runs"
import { cn } from "@/lib/utils"

const failureStatuses = ["failed", "blocked", "error", "cancelled"]

function eventFailed(event: RunEvent) {
  return event.success === false || failureStatuses.includes(event.status ?? "")
}

function eventTitle(event: RunEvent) {
  if (event.action?.startsWith("fill_form:")) {
    return `Filled ${event.action.split(":")[1]} fields`
  }
  if (event.action === "click") return `Clicked ${event.element ?? "element"}`
  if (event.action === "fill") return `Filled ${event.element ?? "field"}`
  if (event.action === "select_option") return "Selected an option"
  if (event.action === "set_checked") return "Updated a selection"
  if (event.action === "scroll") return "Scrolled the page"
  if (event.action?.startsWith("assert_")) {
    return `Verified ${event.action.slice(7).replaceAll("_", " ")}`
  }
  if (event.action) return event.action.replaceAll("_", " ")
  if (event.status) return `Run ${event.status}`
  return event.success === false ? "Assertion failed" : "Assertion passed"
}

function eventDescription(event: RunEvent) {
  const descriptions: Record<string, string> = {
    fields_updated: "Updated the selected form fields.",
    page_may_have_changed: "The page responded to the browser action.",
    asserted: "The expected condition was verified.",
  }
  return event.message
    ? (descriptions[event.message] ?? event.message)
    : "Event completed successfully."
}

function EventIcon({ event, active }: { event: RunEvent; active: boolean }) {
  if (eventFailed(event)) return <XIcon className="size-3.5" />
  if (active) return <Spinner className="size-3.5" />
  return <CheckIcon className="size-3.5" />
}

function EventTime({ event }: { event: RunEvent }) {
  const failed = eventFailed(event)
  const running = event.status === "running"

  return (
    <Badge
      variant={failed ? "destructive" : "outline"}
      className={cn(
        "h-4.5 px-1 py-0.5 text-[0.625rem] leading-none",
        !failed &&
          (running
            ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-300"
            : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300")
      )}
    >
      {new Date(event.created_at).toLocaleTimeString()}
    </Badge>
  )
}

export function RunEvents({ events }: { events: RunEvent[] }) {
  if (!events.length) {
    return <p className="text-sm text-muted-foreground">Waiting for events…</p>
  }

  return (
    <div className="flex flex-col">
      {events.map((event, index) => {
        const failed = eventFailed(event)
        const active = index === events.length - 1 && event.status === "running"

        return (
          <div
            key={event.id}
            className={cn(
              "relative ms-10 flex flex-col gap-0.5 last:pb-0",
              event.kind === "action" ? "pb-10" : "pb-6"
            )}
          >
            {index < events.length - 1 && (
              <div
                aria-hidden
                className="absolute -left-7 top-7 h-[calc(100%-1.75rem)] w-0.5 -translate-x-1/2 bg-primary"
              />
            )}
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold capitalize">
                  {eventTitle(event)}
                </h3>
                <EventTime event={event} />
              </div>
              <div
                aria-hidden
                className={cn(
                  "absolute top-0 -left-7 flex size-6 -translate-x-1/2 items-center justify-center rounded-full bg-primary text-primary-foreground",
                  active && "ring-2 ring-primary/20",
                  failed && "bg-destructive text-white"
                )}
              >
                <EventIcon event={event} active={active} />
              </div>
            </div>
            {event.kind === "action" && (
              <div className="mt-2 text-sm text-muted-foreground">
                <div className="rounded-xl border bg-muted/50">
                  <Collapsible defaultOpen className="group/collapsible">
                    <CollapsibleTrigger className="flex w-full">
                      <div className="flex grow flex-row items-center justify-between gap-2 px-3 py-1.5">
                        <div className="flex min-w-0 items-center gap-2">
                          <CircleDotIcon className="size-4 shrink-0 text-muted-foreground" />
                          <span className="truncate text-xs font-medium text-muted-foreground capitalize">
                            {event.element ?? "Browser action"}
                          </span>
                        </div>
                        <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-open/collapsible:rotate-90" />
                      </div>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="rounded-xl border bg-card px-3 py-3.5 shadow-xs">
                        <p className="text-sm leading-relaxed text-muted-foreground">
                          {eventDescription(event)}
                        </p>
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                </div>
              </div>
            )}
            {event.kind === "assertion" && (
              <div className="mt-1 text-xs leading-relaxed break-words text-muted-foreground">
                {eventDescription(event)}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
