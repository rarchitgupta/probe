"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Controller, useForm } from "react-hook-form"
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
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { type EnvironmentValue, useCreateEnvironment } from "@/lib/runs"

const lines = z.string().refine(
  (value) =>
    value
      .split("\n")
      .filter((line) => line.trim())
      .every((line) => line.includes("=")),
  "Use one NAME=value entry per line."
)

const schema = z.object({
  name: z.string().trim().min(1).max(100),
  viewport_width: z.number().int().min(320).max(3840),
  viewport_height: z.number().int().min(240).max(2160),
  headers: lines,
  cookies: lines,
  secrets: lines,
})

type Values = z.infer<typeof schema>

function entries(value: string) {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const separator = line.indexOf("=")
      return [line.slice(0, separator).trim(), line.slice(separator + 1).trim()]
    })
}

function configuredValue(value: string): EnvironmentValue {
  return value.startsWith("$") ? { env: value.slice(1) } : { value }
}

export function EnvironmentForm() {
  const mutation = useCreateEnvironment()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      viewport_width: 1280,
      viewport_height: 720,
      headers: "",
      cookies: "",
      secrets: "",
    },
  })

  function submit(values: Values) {
    mutation.mutate(
      {
        name: values.name,
        viewport_width: values.viewport_width,
        viewport_height: values.viewport_height,
        definition: {
          headers: Object.fromEntries(
            entries(values.headers).map(([name, value]) => [
              name,
              configuredValue(value),
            ])
          ),
          cookies: entries(values.cookies).map(([name, value]) => ({
            name,
            value: configuredValue(value),
          })),
          secrets: Object.fromEntries(entries(values.secrets)),
        },
      },
      {
        onSuccess: () => {
          toast.success("Environment created")
          form.reset()
        },
        onError: (error) =>
          toast.error("Could not create environment", {
            description: error.message,
          }),
      }
    )
  }

  return (
    <Card>
      <form onSubmit={form.handleSubmit(submit)}>
        <CardHeader>
          <CardTitle>New environment</CardTitle>
          <CardDescription>
            Prefix a value with $ to read it from the Probe server environment.
          </CardDescription>
        </CardHeader>
        <CardContent className="my-4">
          <FieldGroup>
            <Controller
              name="name"
              control={form.control}
              render={({ field }) => (
                <Field>
                  <FieldLabel>Name</FieldLabel>
                  <Input {...field} placeholder="Staging" />
                </Field>
              )}
            />
            <div className="grid gap-4 sm:grid-cols-2">
              {(["viewport_width", "viewport_height"] as const).map((name) => (
                <Controller
                  key={name}
                  name={name}
                  control={form.control}
                  render={({ field }) => (
                    <Field>
                      <FieldLabel>
                        {name === "viewport_width" ? "Width" : "Height"}
                      </FieldLabel>
                      <Input
                        {...field}
                        type="number"
                        onChange={(event) =>
                          field.onChange(event.target.valueAsNumber)
                        }
                      />
                    </Field>
                  )}
                />
              ))}
            </div>
            {(["headers", "cookies", "secrets"] as const).map((name) => (
              <Controller
                key={name}
                name={name}
                control={form.control}
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.invalid}>
                    <FieldLabel className="capitalize">{name}</FieldLabel>
                    <Textarea
                      {...field}
                      rows={3}
                      placeholder={
                        name === "secrets"
                          ? "password=SAUCE_PASSWORD"
                          : "Authorization=$STAGING_TOKEN"
                      }
                    />
                    {fieldState.error && (
                      <p className="text-xs text-destructive">
                        {fieldState.error.message}
                      </p>
                    )}
                  </Field>
                )}
              />
            ))}
          </FieldGroup>
        </CardContent>
        <CardFooter className="justify-end">
          <Button disabled={mutation.isPending} type="submit">
            {mutation.isPending ? "Creating…" : "Create environment"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
