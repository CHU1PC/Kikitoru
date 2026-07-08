import { ApiErrorBody } from "./schemas"
import type { SummaryResponse, SummaryPageResponse, UserPublic, UserAdminUpdate, UserStatusKey, TranscriptSegmentResponse } from "../gen/types"
import {
    summaryResponseSchema,
    summaryPageResponseSchema,
    getTranscriptEndpointApiV1SummariesSummaryIdTranscriptGetResponseSchema as transcriptListSchema,
} from "../gen/zod"


const API_BASE = "http://localhost:8000"


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


export async function getSummary(id: string): Promise<SummaryResponse> {
    const res = await fetch(
        `${API_BASE}/api/v1/summaries/${id}`, 
        {credentials: "include",}
    )

    await throwIfNotOk(res)
    const json = await res.json()
    return summaryResponseSchema.parse(json)
}

export async function getTranscript(id: string): Promise<TranscriptSegmentResponse[]> {
    const res = await fetch(
        `${API_BASE}/api/v1/summaries/${id}/transcript`,
        {credentials: "include",}
    )
    await throwIfNotOk(res)
    const json = await res.json()
    return transcriptListSchema.parse(json)
}

export async function getSummaries(limit: number = 50, offset: number = 0): Promise<SummaryPageResponse> {
    const params = new URLSearchParams({limit: limit.toString(), offset: offset.toString()})
    const res = await fetch(
        `${API_BASE}/api/v1/summaries?${params}`,
        {credentials: "include",}
    )
    await throwIfNotOk(res)
    const json = await res.json()
    return summaryPageResponseSchema.parse(json)
}


type UploadAudioInput = {
    file: File
    recorded_at?: string
    num_speakers?: number
}


export async function uploadAudio(input: UploadAudioInput): Promise<SummaryResponse> {
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
    return summaryResponseSchema.parse(json)
}


export async function getMe(): Promise<UserPublic | null> {
    const res = await fetch(`${API_BASE}/auth/me`, {credentials: "include"})
    if (res.status === 401) return null
    await throwIfNotOk(res)
    return res.json()
}


export async function logout(): Promise<void> {
    const res = await fetch(`${API_BASE}/auth/logout`, {method: "POST", credentials: "include"})
    await throwIfNotOk(res)
}


export function startGoogleLogin(): void {
    window.location.href = `${API_BASE}/auth/google/start`
}


export async function listUsers(status?: UserStatusKey): Promise<UserPublic[]> {
    // status が null の場合は全ステータスのユーザーを取得する
    const url = new URL(`${API_BASE}/api/v1/admin/users`)
    if (status) url.searchParams.set("status", status)
    const res = await fetch(url, {credentials: "include"})
    await throwIfNotOk(res)
    return res.json()
}


export async function updateUser(userId: string, payload: UserAdminUpdate): Promise<UserPublic> {
    const res = await fetch(`${API_BASE}/api/v1/admin/users/${userId}`, {
        method: "PATCH",
        headers: {"Content-Type": "application/json"},
        credentials: "include",
        body: JSON.stringify(payload),
    })
    await throwIfNotOk(res)
    return res.json()
}
