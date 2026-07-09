import { useCallback, useEffect, useRef, useState } from "react"
import { ApiError, getJob, listJobs, uploadAudio } from "../api/client"
import type { UploadAudioInput } from "../api/client"
import type { TranscriptionJobResponse } from "../gen/types"

const POLL_INTERVAL_MS = 3000
const TEMP_PREFIX = "temp-"
const ACTIVE = new Set(["pending", "processing"])

export function useJobs(onCompleted: (summaryId?: string | null) => void) {
    const [jobs, setJobs] = useState<TranscriptionJobResponse[]>([])
    const jobsRef = useRef(jobs)
    const onCompletedRef = useRef(onCompleted)

    useEffect(() => {
        jobsRef.current = jobs
        onCompletedRef.current = onCompleted
    })

    // 再読込耐性: マウント時にサーバの進行中 job を復元
    useEffect(() => {
        let active = true
        listJobs()
            .then((js) => { if (active) setJobs(js) })
            .catch(() => {})
        return () => { active = false }
    }, [])


    const hasActive = jobs.some((j) => ACTIVE.has(j.status))

    // 進行中 job がある間だけ polling
    useEffect(() => {
        if (!hasActive) return
        let stopped = false

        const poll = async () => {
            const active = jobsRef.current.filter(
                (j) => ACTIVE.has(j.status) && !j.id.startsWith(TEMP_PREFIX),
            )
            for (const j of active) {
                let updated: TranscriptionJobResponse
                try {
                    updated = await getJob(j.id)
                } catch {
                    continue
                }
                if (stopped) return
                if (updated.status === "completed") {
                    setJobs((prev) => prev.filter((x) => x.id !== j.id))
                    onCompletedRef.current()
                } else if (updated.status !== j.status) {
                    setJobs((prev) => prev.map((x) => (x.id === j.id ? updated : x)))
                }
            }
        }

        const interval = setInterval(poll, POLL_INTERVAL_MS)
        return () => {
            stopped = true
            clearInterval(interval)
        }
    }, [hasActive])

    const startUpload = useCallback((input: UploadAudioInput) => {
        const tempId = `${TEMP_PREFIX}${crypto.randomUUID()}`
        const optimistic: TranscriptionJobResponse = {
            id: tempId,
            status: "processing",
            filename: input.file.name,
            created_at: new Date().toISOString(),
            summary_id: null,
            error: null,
        }
        setJobs((prev) => [optimistic, ...prev]) // クリック即サイドバー表示

        uploadAudio(input)
            .then((job) => {
                if (job.status === "completed") {
                    // cache hit: optimistic を消して, その要約を開く
                    setJobs((prev) => prev.filter((x) => x.id !== tempId))
                    onCompletedRef.current(job.summary_id)
                } else {
                    // 本物の job に差し替え (以降 polling は本物の id で走る)
                    setJobs((prev) => prev.map((x) => (x.id === tempId ? job : x)))
                }
            })
            .catch((err) => {
                const detail = err instanceof ApiError ? err.detail : "アップロードに失敗しました"
                setJobs((prev) =>
                    prev.map((x) => (x.id === tempId ? { ...x, status: "failed", error: detail } : x)),
                )
            })
    }, [])

    return { jobs, startUpload }
}
