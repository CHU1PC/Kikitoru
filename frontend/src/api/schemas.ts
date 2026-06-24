import { z } from "zod"

export const Topic = z.object({
    title: z.string(),
    summary: z.string(),
})

export const Decision = z.object({
    description: z.string(),
    decided_by: z.string().nullable(),
})

export const ActionItem = z.object({
    description: z.string(),
    assignee: z.string().nullable(),
    due_date: z.iso.date().nullable(),
})

export const SummaryListItem = z.object({
    id: z.uuid(),
    filename: z.string(),
    created_at: z.iso.datetime(),
    overall_summary: z.string(),
})

export const Summary = SummaryListItem.extend({
    topics: z.array(Topic),
    decisions: z.array(Decision),
    action_items: z.array(ActionItem),
})

export const SummaryListResponse = z.object({
    items: z.array(SummaryListItem),
    total: z.int(),
    limit: z.int(),
    offset: z.int(),
})

export type Topic = z.infer<typeof Topic>
export type Decision = z.infer<typeof Decision>
export type ActionItem = z.infer<typeof ActionItem>
export type SummaryListItem = z.infer<typeof SummaryListItem>
export type Summary = z.infer<typeof Summary>
export type SummaryListResponse = z.infer<typeof SummaryListResponse>


export const ApiErrorBody = z.object({
    detail: z.string(),
})
