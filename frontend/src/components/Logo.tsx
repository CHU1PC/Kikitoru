type Props = {
  size?: number
  className?: string
}

// Kikitoru ロゴ: 吹き出し + 波形 (会話を文字起こし)。色はテーマ変数に追従する。
export function Logo({ size = 30, className }: Props) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      aria-hidden="true"
    >
      <path
        d="M4 4h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-7l-5 4v-4H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"
        fill="var(--accent)"
      />
      <g stroke="var(--bg)" strokeWidth="1.8" strokeLinecap="round">
        <line x1="7" y1="10.5" x2="7" y2="12.5" />
        <line x1="10" y1="8.5" x2="10" y2="14.5" />
        <line x1="13" y1="9.5" x2="13" y2="13.5" />
        <line x1="16" y1="10.5" x2="16" y2="12.5" />
      </g>
    </svg>
  )
}
