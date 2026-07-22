import { useEffect, useState } from "react"
import { getTranscript } from "../api/client"
import type { TranscriptSegmentResponse } from "../gen/types"

/**
 * summary の文字起こしを遅延取得するフック.
 * enabled=true (文字起こしタブを開いた時) のみ取得. summaryId 変更で取り直す.
 * loading は「まだ現 summaryId を読めていない」から導出 (effect 同期部で setState しない).
 * race は active フラグで防ぐ (古い応答を無視).
 */
export function useTranscript(summaryId: string, enabled: boolean) {
    const [segments, setSegments] = useState<TranscriptSegmentResponse[]>([])
    const [doneId, setDoneId] = useState<string | null>(null)
    const [failed, setFailed] = useState(false)

    useEffect(() => {
        if (!enabled) return
        let active = true
        getTranscript(summaryId)
            .then((segs) => {
                if (!active) return
                setSegments(segs)
                setFailed(false)
                setDoneId(summaryId)
            })
            .catch(() => {
                if (!active) return
                setFailed(true)
                setDoneId(summaryId)
            })
        return () => {
            active = false
        }
    }, [summaryId, enabled])

    const loading = enabled && doneId !== summaryId
    const error = failed && doneId === summaryId
    return { segments, loading, error }
}
