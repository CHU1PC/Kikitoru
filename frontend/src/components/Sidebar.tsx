import type { SummaryListItem } from "../gen/types"
import { formatShortDate } from "../utils/date"

type Props = {
    items: SummaryListItem[]
    activeId: string | null
    loading?: boolean
    error?: boolean
    onSelect: (id: string) => void
    onNew: () => void
    onRetry?: () => void
}

function titleOf(filename: string): string {
    const base = filename
        .replace(/^\d{4}-\d{2}-\d{2}[_-]/, "")
        .replace(/\.[^.]+$/, "")
    return base || filename
}


export function Sidebar({ items, activeId, loading, error, onSelect, onNew, onRetry }: Props) {
    return (
        <aside className="sidebar">
            <div className="sb-top">
            <button type="button" className="newbtn" onClick={onNew}>
                <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.4"
                    strokeLinecap="round"
                >
                    <path d="M12 5v14M5 12h14" />
                </svg>
                新規要約
                </button>
            </div>

            <div className="sb-label">履歴</div>

            {/* sb-top / newbtn / sb-label は既存のまま */}
            <div className="histlist">
                {loading ? (
                    <p className="hist-empty">読み込み中...</p>
                ) : error ? (
                    <div className="hist-error">
                        <span>一覧の取得に失敗しました</span>
                        {onRetry && (
                            <button type="button" className="ghost" onClick={onRetry}>
                                再試行
                            </button>
                        )}
                    </div>
                ) : items.length === 0 ? (
                    <p className="hist-empty">まだ要約がありません</p>
                ) : (
                    items.map((item) => (
                        <button
                            key={item.id}
                            type="button"
                            className={`histitem${item.id === activeId ? " active" : ""}`}
                            onClick={() => onSelect(item.id)}
                        >
                            <span className="hi-title">{titleOf(item.filename)}</span>
                            <span className="hi-meta num">{formatShortDate(item.created_at)}</span>
                        </button>
                    ))
                )}
            </div>
        </aside>
    )
}
