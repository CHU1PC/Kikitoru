import { useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

type Props = {
    value: string
    onChange: (value: string) => void
}

const DOW = ["日", "月", "火", "水", "木", "金", "土"]

function pad(n: number): string {
    return String(n).padStart(2, "0")
}

function toIso(d: Date): string {
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function parse(value: string): Date | null {
    if (!value) return null
    const d = new Date(`${value}T00:00:00`)
    return Number.isNaN(d.getTime()) ? null : d
}

export function DatePicker({ value, onChange }: Props) {
    const selected = parse(value)
    const [open, setOpen] = useState(false)
    const [view, setView] = useState(() => selected ?? new Date())
    const [pos, setPos] = useState({ top: 0, left: 0 })
    const triggerRef = useRef<HTMLButtonElement>(null)
    const calRef = useRef<HTMLDivElement>(null)

    function openCal() {
        const rect = triggerRef.current?.getBoundingClientRect()
        if (rect) setPos({ top: rect.bottom + 8, left: rect.left })
        setView(selected ?? new Date())
        setOpen(true)
    }

    useEffect(() => {
        if (!open) return
        function onDown(e: MouseEvent) {
            const t = e.target as Node
            if (triggerRef.current?.contains(t) || calRef.current?.contains(t)) return
            setOpen(false)
        }
        function onKey(e: KeyboardEvent) {
            if (e.key === "Escape") setOpen(false)
        }
        function onScrollResize() {
            setOpen(false)
        }
        document.addEventListener("mousedown", onDown)
        document.addEventListener("keydown", onKey)
        window.addEventListener("scroll", onScrollResize, true)
        window.addEventListener("resize", onScrollResize)
        return () => {
            document.removeEventListener("mousedown", onDown)
            document.removeEventListener("keydown", onKey)
            window.removeEventListener("scroll", onScrollResize, true)
            window.removeEventListener("resize", onScrollResize)
        }
    }, [open])

    const year = view.getFullYear()
    const month = view.getMonth()
    const firstDow = new Date(year, month, 1).getDay()
    const daysInMonth = new Date(year, month + 1, 0).getDate()

    function pick(day: number) {
        onChange(toIso(new Date(year, month, day)))
        setOpen(false)
    }

    return (
        <div className="datepick">
            <button
                type="button"
                ref={triggerRef}
                className="date-trigger"
                onClick={() => (open ? setOpen(false) : openCal())}
            >
                <svg
                    className="date-icon"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                >
                    <rect x="3" y="4" width="18" height="18" rx="2" />
                    <path d="M16 2v4M8 2v4M3 10h18" />
                </svg>
                {selected ? (
                    <span>
                        {selected.getFullYear()}/{pad(selected.getMonth() + 1)}/
                        {pad(selected.getDate())}
                    </span>
                ) : (
                    <span className="placeholder">選択</span>
                )}
            </button>

            {open &&
                createPortal(
                    <div
                        ref={calRef}
                        className="calendar"
                        style={{ top: pos.top, left: pos.left }}
                    >
                        <div className="cal-head">
                            <button
                                type="button"
                                className="cal-nav"
                                onClick={() => setView(new Date(year, month - 1, 1))}
                            >
                                ‹
                            </button>
                            <span className="cal-title">
                                {year}年 {month + 1}月
                            </span>
                            <button
                                type="button"
                                className="cal-nav"
                                onClick={() => setView(new Date(year, month + 1, 1))}
                            >
                                ›
                            </button>
                        </div>

                        <div className="cal-grid cal-dow">
                            {DOW.map((d) => (
                                <span key={d}>{d}</span>
                            ))}
                        </div>

                        <div className="cal-grid">
                            {Array.from({ length: firstDow }).map((_, i) => (
                                <span key={`empty-${i}`} className="cal-day is-empty" />
                            ))}
                            {Array.from({ length: daysInMonth }).map((_, i) => {
                                const day = i + 1
                                const isSel =
                                    selected !== null &&
                                    selected.getFullYear() === year &&
                                    selected.getMonth() === month &&
                                    selected.getDate() === day
                                return (
                                    <button
                                        key={day}
                                        type="button"
                                        className={`cal-day${isSel ? " is-selected" : ""}`}
                                        onClick={() => pick(day)}
                                    >
                                        {day}
                                    </button>
                                )
                            })}
                        </div>
                    </div>,
                    document.body,
                )}
        </div>
    )
}
