import { Summary } from "./schemas"

const API_BASE = "http://localhost:8000"

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
