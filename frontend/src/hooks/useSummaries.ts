import { useCallback, useEffect, useState } from "react"
import { getSummaries, getSummary } from "../api/client"
import type { SummaryListItem, SummaryResponse } from "../gen/types"

/**
 * 履歴一覧 + 選択中の詳細を扱うフック.
 * Workspace (承認後の画面) でのみ呼ばれるので mount = 承認後.
 */
export function useSummaries() {
    const [items, setItems] = useState<SummaryListItem[]>([])
    const [activeId, setActiveId] = useState<string | null>(null)
    const [detail, setDetail] = useState<SummaryResponse | null>(null)

    useEffect(() => {
        getSummaries()
            .then((page) => setItems(page.items))
            .catch(() => setItems([]))
    }, [])

    const select = useCallback(async (id: string) => {
        setActiveId(id)
        setDetail(await getSummary(id))
    }, [])

    const startNew = useCallback(() => {
        setActiveId(null)
        setDetail(null)
    }, [])

    const addUploaded = useCallback((summary: SummaryResponse) => {
        const item: SummaryListItem = {
            id: summary.id,
            filename: summary.filename,
            created_at: summary.created_at,
            overall_summary: summary.overall_summary,
            group_id: summary.group_id,
        }
        setItems((prev) => [item, ...prev])
        setActiveId(summary.id)
        setDetail(summary)
    }, [])

    return { items, activeId, detail, select, startNew, addUploaded }
}