import { Summary, SummaryListResponse, ApiErrorBody } from "./schemas"

const API_BASE = "http://localhost:8000"

type UploadAudioInput = {
    file: File
    recorded_at?: string
    num_speakers?: number
}

export class ApiError extends Error {
    status: number
    detail: string

    constructor(status: number, detail: string) {
        super(detail)
        this.name = "ApiError"
        this.status = status
        this.detail = detail
    }
}

async function throwIfNotOk(res: Response): Promise<void> {
    if(res.ok) return
    const body = await res.json().catch(() => ({}))
    const parsed = ApiErrorBody.safeParse(body)
    const detail = parsed.success ? parsed.data.detail : `HTTP ${res.status}`
    throw new ApiError(res.status, detail)
}


export async function getSummary(id: string): Promise<Summary> {
    const res = await fetch(
        `${API_BASE}/api/v1/summaries/${id}`, 
        {credentials: "include",}
    )

    await throwIfNotOk(res)
    const json = await res.json()
    return Summary.parse(json)
}

export async function getSummaries(limit: number = 50, offset: number = 0): Promise<SummaryListResponse> {
    const params = new URLSearchParams({limit: limit.toString(), offset: offset.toString()})
    const res = await fetch(
        `${API_BASE}/api/v1/summaries?${params}`,
        {credentials: "include",}
    )
    await throwIfNotOk(res)
    const json = await res.json()
    return SummaryListResponse.parse(json)
}


export async function uploadAudio(input: UploadAudioInput): Promise<Summary> {
    const formData = new FormData()
    formData.append("file", input.file)
    if (input.recorded_at) {
        formData.append("recorded_at", input.recorded_at)
    }
    if (input.num_speakers !== undefined) {
        formData.append("num_speakers", input.num_speakers.toString())
    }

    const res = await fetch(
        `${API_BASE}/api/v1/audio/summarize`, 
        {
            method: "POST",
            body: formData,
            credentials: "include",
        }
    )

    await throwIfNotOk(res)
    const json = await res.json()
    return Summary.parse(json)
}
