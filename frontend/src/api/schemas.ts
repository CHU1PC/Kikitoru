import { z } from "zod"

export const ApiErrorBody = z.object({
    detail: z.string(),
})
