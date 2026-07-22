import { useCallback, useEffect, useRef, useState } from "react"
import { getSummaries, getSummary } from "../api/client"
import type { SummaryListItem, SummaryResponse } from "../gen/types"

/**
 * 履歴一覧 + 選択中の詳細を扱うフック.
 * Workspace (承認後の画面) でのみ呼ばれるので mount = 承認後.
 */
export function useSummaries() {
    const [items, setItems] = useState<SummaryListItem[]>([])
    const [listLoading, setListLoading] = useState(true)
    const [listError, setListError] = useState(false)
    const [activeId, setActiveId] = useState<string | null>(null)
    const [detail, setDetail] = useState<SummaryResponse | null>(null)
    const latestReq = useRef(0)

    const loadList = useCallback(() => {
        getSummaries()
            .then((page) => setItems(page.items))
            .catch(() => setListError(true))
            .finally(() => setListLoading(false))
    }, [])

    const retryLoad = useCallback(() => {
        setListLoading(true)
        setListError(false)
        loadList()
    }, [loadList])

    useEffect(() => {
        loadList()
    }, [loadList])

    const select = useCallback(async (id: string) => {
        const reqId = ++latestReq.current
        setActiveId(id)
        try {
            const full = await getSummary(id)
            if (latestReq.current === reqId) setDetail(full)
        } catch {
            if (latestReq.current === reqId) setDetail(null)
        }
    }, [])

    const startNew = useCallback(() => {
        setActiveId(null)
        setDetail(null)
    }, [])

    return { items, listLoading, listError, activeId, detail, select, startNew, reloadList: retryLoad }
}