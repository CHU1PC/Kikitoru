import { formatTimestamp } from "../utils/date"
import { Spinner } from "./Spinner"
import type { TranscriptSegmentResponse } from "../gen/types"

type Props = {
    segments: TranscriptSegmentResponse[]
    loading: boolean
    error: boolean
}

export function Transcript({ segments, loading, error }: Props) {
    if (loading) return <Spinner label="文字起こしを読み込み中..." />
    if (error) return <p className="ts-empty">文字起こしの取得に失敗しました</p>
    if (segments.length === 0)
        return <p className="ts-empty">文字起こしがありません</p>

    return (
        <div className="transcript">
            {segments.map((seg) => (
                <div className="ts-seg" key={seg.id}>
                    <div className="ts-head">
                        <span className="ts-speaker">{seg.speaker_label}</span>
                        <span className="ts-time num">
                            {formatTimestamp(seg.start_ms)}
                        </span>
                    </div>
                    <p className="ts-text">{seg.text}</p>
                </div>
            ))}
        </div>
    )
}
