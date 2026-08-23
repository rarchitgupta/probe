import {
  Ban,
  CircleAlert,
  CircleCheck,
  CircleX,
  Clock3,
  LoaderCircle,
  OctagonX,
  type LucideIcon,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { type RunStatus } from "@/lib/runs"

const statusBadges: Record<RunStatus, { icon: LucideIcon; className: string }> =
  {
    queued: { icon: Clock3, className: "bg-muted text-muted-foreground" },
    running: {
      icon: LoaderCircle,
      className:
        "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300",
    },
    passed: {
      icon: CircleCheck,
      className:
        "border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-950 dark:text-green-300",
    },
    failed: {
      icon: CircleX,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    blocked: {
      icon: OctagonX,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    error: {
      icon: CircleAlert,
      className:
        "border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-950 dark:text-red-300",
    },
    cancelled: { icon: Ban, className: "bg-muted text-muted-foreground" },
  }

export function StatusBadge({ status }: { status: RunStatus }) {
  const { icon: Icon, className } = statusBadges[status]

  return (
    <Badge variant="outline" className={`font-mono uppercase ${className}`}>
      <Icon data-icon="inline-start" />
      {status}
    </Badge>
  )
}
