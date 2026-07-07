import { useRef, useState, type DragEvent, type SyntheticEvent } from "react"
import { uploadAudio, ApiError } from "../api/client"
import { SpeakerStepper } from "./SpeakerStepper"
import type { SummaryResponse } from "../gen/types"

type Props = {
    onSuccess: (summary: SummaryResponse) => void
}

export function UploadForm({ onSuccess }: Props) {
    const [file, setFile] = useState<File | null>(null)
    const [recordedAt, setRecordedAt] = useState("")
    const [numSpeakers, setNumSpeakers] = useState("2")
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [dragging, setDragging] = useState(false)
    const inputRef = useRef<HTMLInputElement>(null)

    function handleDrop(e: DragEvent<HTMLDivElement>) {
        e.preventDefault()
        setDragging(false)
        const droppedFile = e.dataTransfer.files?.[0]
        if (droppedFile) setFile(droppedFile)
    }

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
        <div className="view-upload">
            <div className="uphead">
                <h2>新規要約</h2>
                <p>会議の音声・動画をアップロードすると議事録を作成します</p>
            </div>

            <form className="upcard" onSubmit={handleSubmit}>
                <div
                    className={`filezone${dragging ? " dragging" : ""}`}
                    onClick={() => inputRef.current?.click()}
                    onDragOver={(e) => {
                        e.preventDefault()
                        setDragging(true)
                    }}
                    onDragLeave={() => setDragging(false)}
                    onDrop={handleDrop}
                >
                    <div className="fz-icon">
                        <svg
                            width="19"
                            height="19"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                        >
                            <path d="M12 15V3" />
                            <path d="m7 8 5-5 5 5" />
                            <path d="M5 21h14" />
                        </svg>
                    </div>
                    <div className="fz-text">
                        <b>{file ? file.name : "音声・動画を選択 / ドロップ"}</b>
                        <span>mp3 · m4a · wav · flac · mp4 · webm — 最大 500MB</span>
                    </div>
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".mp3,.m4a,.wav,.flac,.mp4,.webm"
                        hidden
                        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                </div>

                <div className="upload-row">
                    <div className="mini">
                        <label>録音日（任意）</label>
                        <input
                            className="date-native"
                            type="date"
                            value={recordedAt}
                            onChange={(e) => setRecordedAt(e.target.value)}
                        />
                    </div>
                    <div className="mini">
                        <label>話者数（任意）</label>
                        <SpeakerStepper
                            value={numSpeakers}
                            onChange={setNumSpeakers}
                        />
                    </div>
                    <span className="spacer"></span>
                    <button
                        type="submit"
                        className="primary"
                        disabled={!file || loading}
                    >
                        {loading ? "要約中..." : "要約する"}
                    </button>
                </div>

                {error && <p className="error">{error}</p>}
            </form>
        </div>
    )
}
