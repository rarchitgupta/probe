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
import { Input } from "@/components/ui/input"
import {
  Field,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Textarea } from "@/components/ui/textarea"
import { useCreateRun } from "@/lib/runs"

const formSchema = z.object({
  website: z.url({
    message: "Please enter a valid URL.",
  }),
  instructions: z
    .string()
    .trim()
    .min(10, "Instructions must be at least 10 characters.")
    .max(2000, "Instructions must be 2,000 characters or fewer."),
})

export function URLForm() {
  const createRun = useCreateRun()
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      website: "",
      instructions: "",
    },
  })

  function onSubmit(values: z.infer<typeof formSchema>) {
    createRun.mutate(
      { start_url: values.website, goal: values.instructions },
      {
        onSuccess: ({ id }) => {
          form.reset()
          toast.success("Task queued", { description: `Run ${id}` })
        },
        onError: (error) =>
          toast.error("Could not queue task", {
            description: error.message,
          }),
      }
    )
  }

  return (
    <Card className="w-full">
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <CardHeader>
          <CardTitle>New QA task</CardTitle>
          <CardDescription>
            Create a new QA run for Probe to execute
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
          </FieldGroup>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={createRun.isPending}>
            {createRun.isPending ? "Queuing..." : "Run Task"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  )
}
