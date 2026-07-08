import type { SummaryResponse } from "../gen/types"
import { formatDate } from "../utils/date"

type Props = {
    summary: SummaryResponse
}

export function SummaryView({ summary }: Props) {
    return (
        <div className="summary">
            <div className="sum-head">
                <h2>{summary.filename}</h2>
                <div className="meta">
                    <span className="pill num">{formatDate(summary.created_at)}</span>
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
                {summary.topics.length === 0 && <p className="sec-empty">議題はありません。</p>}
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
                {summary.decisions.length === 0 && <p className="sec-empty">決定事項はありません。</p>}
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
                {summary.action_items.length === 0 && <p className="sec-empty">アクションはありません。</p>}
            </section>
        </div>
    )
}
