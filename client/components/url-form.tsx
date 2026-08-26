"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { useRouter } from "next/navigation"
import { Controller, useForm, useWatch } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Textarea } from "@/components/ui/textarea"
import { useCreateRun, useEnvironments } from "@/lib/runs"

const formSchema = z.object({
  website: z.url({
    message: "Please enter a valid URL.",
  }),
  instructions: z
    .string()
    .trim()
    .min(10, "Instructions must be at least 10 characters.")
    .max(2000, "Instructions must be 2,000 characters or fewer."),
  environment_id: z.string(),
})

export function URLForm() {
  const createRun = useCreateRun()
  const environments = useEnvironments()
  const router = useRouter()
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      website: "",
      instructions: "",
      environment_id: "",
    },
  })
  const environmentId = useWatch({
    control: form.control,
    name: "environment_id",
  })

  function onSubmit(values: z.infer<typeof formSchema>) {
    createRun.mutate(
      {
        start_url: values.website,
        goal: values.instructions,
        environment_id: values.environment_id || undefined,
      },
      {
        onSuccess: ({ id }) => {
          toast.success("Task queued", { description: `Run ${id}` })
          router.push(`/runs/${id}`)
        },
        onError: (error) =>
          toast.error("Could not queue task", {
            description: error.message,
          }),
      }
    )
  }

  const selectedEnvironment = environments.data?.find(
    (environment) => environment.id === environmentId
  )

  return (
    <Card className="w-full">
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <CardHeader>
          <CardTitle>New QA task</CardTitle>
          <CardDescription>
            Describe a focused browser flow and its expected outcome
          </CardDescription>
        </CardHeader>
        <CardContent className="my-4">
          <FieldGroup>
            <Controller
              control={form.control}
              name="website"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="website">Website</FieldLabel>
                  <Input
                    {...field}
                    id="website"
                    className="bg-background"
                    placeholder="https://example.com"
                    type="url"
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && (
                    <FieldError errors={[fieldState.error]} />
                  )}
                </Field>
              )}
            />
            <Controller
              control={form.control}
              name="instructions"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.invalid}>
                  <FieldLabel htmlFor="instructions">Instructions</FieldLabel>
                  <Textarea
                    {...field}
                    id="instructions"
                    placeholder="Log in, add an item to the cart, and verify checkout succeeds."
                    rows={5}
                    aria-invalid={fieldState.invalid}
                  />
                  {fieldState.invalid && (
                    <FieldError errors={[fieldState.error]} />
                  )}
                </Field>
              )}
            />
            <Controller
              control={form.control}
              name="environment_id"
              render={({ field }) => (
                <Field>
                  <FieldLabel htmlFor="environment">Environment</FieldLabel>
                  <select
                    {...field}
                    id="environment"
                    className="h-9 w-full border bg-background px-3 text-sm"
                  >
                    <option value="">Default browser environment</option>
                    {environments.data?.map((environment) => (
                      <option key={environment.id} value={environment.id}>
                        {environment.name}
                      </option>
                    ))}
                  </select>
                  {selectedEnvironment &&
                    Object.keys(selectedEnvironment.definition.secrets).length >
                      0 && (
                      <p className="text-xs text-muted-foreground">
                        Secrets:{" "}
                        {Object.keys(selectedEnvironment.definition.secrets)
                          .map((name) => `{{secret:${name}}}`)
                          .join(", ")}
                      </p>
                    )}
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button type="submit" disabled={createRun.isPending}>
            {createRun.isPending ? "Queuing..." : "Run task"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
