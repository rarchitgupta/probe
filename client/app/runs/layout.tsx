import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Runs",
  description: "Monitor Probe QA runs and review their results.",
}

export default function RunsLayout({ children }: { children: React.ReactNode }) {
  return children
}
