import type { SummaryResponse } from "../gen/types"

type Props = {
    summary: SummaryResponse
}

function shortDate(iso: string): string {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    const y = d.getFullYear()
    const m = String(d.getMonth() + 1).padStart(2, "0")
    const day = String(d.getDate()).padStart(2, "0")
    return `${y}-${m}-${day}`
}

export function SummaryView({ summary }: Props) {
    return (
        <div className="summary">
            <div className="sum-head">
                <h2>{summary.filename}</h2>
                <div className="meta">
                    <span className="pill num">{shortDate(summary.created_at)}</span>
                </div>
            </div>

            <p className="overall">{summary.overall_summary}</p>

            <section className="sec">
                <div className="sec-label">
                    議題 <span className="count num">{summary.topics.length}</span>
                </div>
                {summary.topics.map((topic, i) => (
                    <div className="row" key={i}>
                        <div className="t">{topic.title}</div>
                        <div className="s">{topic.summary}</div>
                    </div>
                ))}
            </section>

            <section className="sec">
                <div className="sec-label">
                    決定事項{" "}
                    <span className="count num">{summary.decisions.length}</span>
                </div>
                {summary.decisions.map((decision, i) => (
                    <div className="drow" key={i}>
                        <span className="tick">✓</span>
                        <span>
                            <span className="dx">{decision.description}</span>
                            {decision.decided_by && (
                                <span className="by">{decision.decided_by}</span>
                            )}
                        </span>
                    </div>
                ))}
            </section>

            <section className="sec">
                <div className="sec-label">
                    アクション{" "}
                    <span className="count num">
                        {summary.action_items.length}
                    </span>
                </div>
                {summary.action_items.map((item, i) => (
                    <div className="arow" key={i}>
                        <span className="abox"></span>
                        <span className="ax">{item.description}</span>
                        {item.assignee && (
                            <span className="who">{item.assignee}</span>
                        )}
                        {item.due_date && (
                            <span className="due num">{item.due_date}</span>
                        )}
                    </div>
                ))}
            </section>
        </div>
    )
}
