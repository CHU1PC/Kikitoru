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


// 音声ないの時刻 (ms) -> mm:ss (1時間以上は hh:mm:ss).
export function formatTimestamp(ms: number): string {
    const total = Math.floor(ms / 1000)
    const s = total % 60
    const m = Math.floor(total / 60) % 60
    const h = Math.floor(total / 3600)
    const mm = String(m).padStart(2, "0")
    const ss = String(s).padStart(2, "0")
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}