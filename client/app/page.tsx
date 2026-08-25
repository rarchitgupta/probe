import { RecentRuns } from "@/components/recent-runs"
import { URLForm } from "@/components/url-form"

export default function Page() {
  return (
    <main className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-6 p-6 lg:p-8">
      <header className="max-w-2xl space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">
          Test your application
        </h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Give Probe a website and describe the flow you want verified. Your
          task will be queued and executed in an isolated browser session.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <URLForm />
        <RecentRuns />
      </section>
    </main>
  )
}
