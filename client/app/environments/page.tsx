import { EnvironmentForm } from "@/components/environment-form"
import { EnvironmentList } from "@/components/environment-list"

export default function EnvironmentsPage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Environments</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Reuse browser configuration across QA runs.
        </p>
      </div>
      <EnvironmentForm />
      <EnvironmentList />
    </main>
  )
}
