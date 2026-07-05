import { useState, type SyntheticEvent } from "react"
import { uploadAudio, ApiError } from "../api/client"
import type { SummaryResponse } from "../gen/types"

type Props = {
    onSuccess: (summary: SummaryResponse) => void
}

export function UploadForm({ onSuccess }: Props) {
    const [file, setFile] = useState<File | null>(null)
    const [recordedAt, setRecordedAt] = useState("")
    const [numSpeakers, setNumSpeakers] = useState("")
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    async function handleSubmit(e: SyntheticEvent<HTMLFormElement>) {
        e.preventDefault()
        if (!file) return

        setLoading(true)
        setError(null)
        try {
            const summary = await uploadAudio({
                file,
                recorded_at: recordedAt || undefined,
                num_speakers: numSpeakers ? Number(numSpeakers) : undefined,
            })
            onSuccess(summary)
        } catch (err) {
            setError(err instanceof ApiError ? err.detail : "予期しないエラーが発生しました")
        } finally {
            setLoading(false)
        }
    }

    return (
        <form className="upload-form" onSubmit={handleSubmit}>
            <label className="field">
            <span>音声 / 動画ファイル (mp3 / m4a / wav / flac / mp4 / webm, 最大 500MB)</span>
            <input
                type="file"
                accept=".mp3,.m4a,.wav,.flac,.mp4,.webm"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            </label>

            <label className="field">
            <span>録音日 (任意)</span>
            <input
                type="date"
                value={recordedAt}
                onChange={(e) => setRecordedAt(e.target.value)}
            />
            </label>

            <label className="field">
            <span>話者数 (任意, 1-10)</span>
            <input
                type="number"
                min={1}
                max={10}
                value={numSpeakers}
                onChange={(e) => setNumSpeakers(e.target.value)}
                />
            </label>

            {error && <p className="error">{error}</p>}

            <button type="submit" disabled={!file || loading}>
                {loading ? "要約中... (数分かかります)" : "アップロードして要約"}
            </button>
        </form>
    )
}
