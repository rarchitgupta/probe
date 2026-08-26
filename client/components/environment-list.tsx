"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { useEnvironments } from "@/lib/runs"

export function EnvironmentList() {
  const environments = useEnvironments()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved environments</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {environments.data?.map((environment) => (
          <div key={environment.id} className="flex justify-between border p-3">
            <div>
              <p className="font-medium">{environment.name}</p>
              <p className="text-xs text-muted-foreground">
                {environment.viewport_width} × {environment.viewport_height}
              </p>
            </div>
            <p className="text-xs text-muted-foreground">
              {Object.keys(environment.definition.headers).length} headers ·{" "}
              {environment.definition.cookies.length} cookies
            </p>
          </div>
        ))}
        {environments.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No environments yet.</p>
        )}
      </CardContent>
    </Card>
  )
}
