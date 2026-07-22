import { Logo } from "./Logo"
import type { UserPublic } from "../gen/types"

type Props = {
  // approved はここに来ない (App 側で出し分け済み)
  status: UserPublic["status"]
  onLogout: () => void
}

const NOTICE: Record<string, { label: string; body: string }> = {
  pending: {
    label: "承認待ち",
    body: "アカウントは管理者の承認待ちです。承認されるまでしばらくお待ちください。",
  },
  rejected: {
    label: "アクセス拒否",
    body: "このアカウントはアクセスを許可されていません。管理者にお問い合わせください。",
  },
}

export function AccessNotice({ status, onLogout }: Props) {
  const notice = NOTICE[status] ?? NOTICE.rejected
  return (
    <main className="auth-screen">
      <section className="login-card">
        <div className="login-mark" aria-hidden="true">
          <Logo size={32} />
        </div>
        <h1 className="login-title">Kikitoru</h1>
        <span className={`notice-badge status-${status}`}>{notice.label}</span>
        <p className="login-tagline">{notice.body}</p>
        <button type="button" className="ghost-btn" onClick={onLogout}>
          ログアウト
        </button>
      </section>
    </main>
  )
}
