function parse(iso: string): Date | null {
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? null : d
}

function pad(n: number): string {
    return String(n).padStart(2, "0")
}

// MM-DD (履歴一覧用). 閲覧者のローカル日付
export function formatShortDate(iso: string): string {
    const d = parse(iso)
    if (!d) return "-"
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

// YYYY-MM-DD (履歴詳細用). 閲覧者のローカル日付
export function formatDate(iso: string): string {
    const d = parse(iso)
    if (!d) return "-"
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
