import type { SummaryRead } from "../gen/types"

type Props = {
    summary: SummaryRead
}

export function SummaryView({ summary }: Props) {
    return (
        <article className="summary">
            <h2>{summary.filename}</h2>
            <p>{summary.overall_summary}</p>
            <h3>議題</h3>
            <ul>
                {summary.topics.map((topic, i) => (
                    <li key={i}>
                        <strong>{topic.title}</strong>: {topic.summary}
                    </li>
                ))}
            </ul>
            <h3>決定事項</h3>
            <ul>
                {summary.decisions.map((decision, i) => (
                    <li key={i}>
                        {decision.description}
                        {decision.decided_by && <span> ({decision.decided_by})</span>}
                    </li>
                ))}
            </ul>
            <h3>アクションアイテム</h3>
            <ul>
                {summary.action_items.map((item, i) => (
                    <li key={i}>
                        {item.description}
                        {item.assignee && <span> / 担当: {item.assignee}</span>}
                        {item.due_date && <span> / 期限: {item.due_date}</span>}
                    </li>
                ))}
            </ul>
        </article>
    )
}