import { Summary } from "./schemas"

const API_BASE = "http://localhost:8000"

type UploadAudioInput = {
    file: File
    recorded_at?: string
    num_speakers?: number
}

export async function getSummary(id: string): Promise<Summary> {
    const res = await fetch(
        `${API_BASE}/api/v1/summaries/${id}`, 
        {credentials: "include",}
    )

    if (!res.ok) {
        throw new Error(`API error: ${res.status}`)
    }

    const json = await res.json()
    return Summary.parse(json)
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

    if (!res.ok) {
        throw new Error(`API error: ${res.status}`)
    }

    const json = await res.json()
    return Summary.parse(json)
}