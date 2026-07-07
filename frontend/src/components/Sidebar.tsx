import type { SummaryListItem } from "../gen/types"

type Props = {
    items: SummaryListItem[]
    activeId: string | null
    onSelect: (id: string) => void
    onNew: () => void
}

function titleOf(filename: string): string {
    const base = filename
        .replace(/^\d{4}-\d{2}-\d{2}[_-]/, "")
        .replace(/\.[^.]+$/, "")
    return base || filename
}

function shortDate(iso: string): string {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return ""
    const mm = String(d.getMonth() + 1).padStart(2, "0")
    const dd = String(d.getDate()).padStart(2, "0")
    return `${mm}-${dd}`
}


export function Sidebar({ items, activeId, onSelect, onNew }: Props) {
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

            <div className="histlist">
                {items.length === 0 ? (
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
                            <span className="hi-meta num">{shortDate(item.created_at)}</span>
                        </button>
                    ))
                )}
            </div>
        </aside>
    )
}