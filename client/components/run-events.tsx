import { CheckIcon, ChevronRightIcon, CircleDotIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/reui/badge"
import { Frame, FrameHeader, FramePanel } from "@/components/reui/frame"
import {
  Timeline,
  TimelineContent,
  TimelineHeader,
  TimelineIndicator,
  TimelineItem,
  TimelineSeparator,
  TimelineTitle,
} from "@/components/reui/timeline"
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
  const variant = eventFailed(event)
    ? "destructive-light"
    : event.status === "running"
      ? "info-light"
      : "success-light"

  return (
    <Badge variant={variant} size="sm">
      {new Date(event.created_at).toLocaleTimeString()}
    </Badge>
  )
}

export function RunEvents({ events }: { events: RunEvent[] }) {
  if (!events.length) {
    return <p className="text-sm text-muted-foreground">Waiting for events…</p>
  }

  return (
    <Timeline value={events.length}>
      {events.map((event, index) => {
        const failed = eventFailed(event)
        const active = index === events.length - 1 && event.status === "running"

        return (
          <TimelineItem
            key={event.id}
            step={index + 1}
            className={cn(
              "ms-10 last:pb-0",
              event.kind === "action" ? "pb-10" : "pb-6"
            )}
          >
            <TimelineHeader>
              <TimelineSeparator className="group-data-[orientation=vertical]/timeline:-left-7 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem-0.25rem)] group-data-[orientation=vertical]/timeline:translate-y-7" />
              <div className="flex flex-wrap items-center gap-2">
                <TimelineTitle className="text-sm font-semibold capitalize">
                  {eventTitle(event)}
                </TimelineTitle>
                <EventTime event={event} />
              </div>
              <TimelineIndicator
                className={cn(
                  "flex size-6 items-center justify-center border-none bg-primary text-primary-foreground group-data-[orientation=vertical]/timeline:-left-7",
                  active && "ring-2 ring-primary/20",
                  failed && "bg-destructive text-white"
                )}
              >
                <EventIcon event={event} active={active} />
              </TimelineIndicator>
            </TimelineHeader>
            {event.kind === "action" && (
              <TimelineContent className="mt-2">
                <Frame stacked dense spacing="sm">
                  <Collapsible defaultOpen className="group/collapsible">
                    <CollapsibleTrigger className="flex w-full">
                      <FrameHeader className="flex grow flex-row items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <CircleDotIcon className="size-4 shrink-0 text-muted-foreground" />
                          <span className="truncate text-xs font-medium text-muted-foreground capitalize">
                            {event.element ?? "Browser action"}
                          </span>
                        </div>
                        <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-data-open/collapsible:rotate-90" />
                      </FrameHeader>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <FramePanel>
                        <p className="text-sm leading-relaxed text-muted-foreground">
                          {eventDescription(event)}
                        </p>
                      </FramePanel>
                    </CollapsibleContent>
                  </Collapsible>
                </Frame>
              </TimelineContent>
            )}
            {event.kind === "assertion" && (
              <TimelineContent className="mt-1 text-xs leading-relaxed break-words">
                {eventDescription(event)}
              </TimelineContent>
            )}
          </TimelineItem>
        )
      })}
    </Timeline>
  )
}
