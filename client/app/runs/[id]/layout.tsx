import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Run Details",
  description: "Review live progress, results, evidence, and replay.",
}

export default function RunLayout({ children }: { children: React.ReactNode }) {
  return children
}
