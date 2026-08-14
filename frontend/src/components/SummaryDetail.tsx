import { useState } from "react"
import { SummaryView } from "./SummaryView"
import { Transcript } from "./Transcript"
import { useTranscript } from "../hooks/useTranscript"
import type { SummaryResponse } from "../gen/types"

type Tab = "summary" | "transcript"

type Props = {
    summary: SummaryResponse
}

export function SummaryDetail({ summary }: Props) {
    const [tab, setTab] = useState<Tab>("summary")
    const { segments, loading, error } = useTranscript(
        summary.id,
        tab === "transcript",
    )

    return (
        <div className="detail">
            <div className="detail-tabs">
                <button
                    type="button"
                    className={`detail-tab${tab === "summary" ? " active" : ""}`}
                    onClick={() => setTab("summary")}
                >
                    要約
                </button>
                <button
                    type="button"
                    className={`detail-tab${tab === "transcript" ? " active" : ""}`}
                    onClick={() => setTab("transcript")}
                >
                    文字起こし
                </button>
            </div>

            {tab === "summary" ? (
                <SummaryView summary={summary} />
            ) : (
                <Transcript segments={segments} loading={loading} error={error} />
            )}
        </div>
    )
}
