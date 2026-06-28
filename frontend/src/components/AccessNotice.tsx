import type { UserPublic } from "../gen/types"

type Props = {
  // approved はここに来ない (App 側で出し分け済み) が、型は UserPublic と揃える
  status: UserPublic["status"]
  onLogout: () => void
}

const MESSAGES: Record<string, { title: string; body: string }> = {
  pending: {
    title: "承認待ち",
    body: "アカウントは管理者の承認待ちです。承認されるまでしばらくお待ちください。",
  },
  rejected: {
    title: "アクセスが拒否されました",
    body: "このアカウントはアクセスを許可されていません。管理者にお問い合わせください。",
  },
}

export function AccessNotice({ status, onLogout }: Props) {
  const message = MESSAGES[status] ?? MESSAGES.rejected
  return (
    <main className="auth-screen">
      <div className="auth-card">
        <h1>Kikitoru</h1>
        <h2 className="notice-title">{message.title}</h2>
        <p className="auth-lead">{message.body}</p>
        <button type="button" className="ghost-btn" onClick={onLogout}>
          ログアウト
        </button>
      </div>
    </main>
  )
}
