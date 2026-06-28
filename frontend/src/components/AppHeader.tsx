import type { UserPublic } from "../gen/types"
import { Logo } from "./Logo"

type View = "main" | "admin"

type Props = {
  user: UserPublic
  onLogout: () => void
  view?: View
  onChangeView?: (view: View) => void
}

export function AppHeader({ user, onLogout, view = "main", onChangeView }: Props) {
  return (
    <header className="app-header">
      <div className="app-header-brand">
        <Logo size={26} />
        <h1 className="app-header-title">Kikitoru</h1>
      </div>

      {user.role === "admin" && onChangeView && (
        <nav className="app-header-nav">
          <button
            type="button"
            className={`nav-link${view === "main" ? " active" : ""}`}
            onClick={() => onChangeView("main")}
          >
            要約
          </button>
          <button
            type="button"
            className={`nav-link${view === "admin" ? " active" : ""}`}
            onClick={() => onChangeView("admin")}
          >
            ユーザー管理
          </button>
        </nav>
      )}

      <div className="app-header-user">
        <span className="user-name">{user.name || user.email}</span>
        {user.role === "admin" && <span className="role-badge">admin</span>}
        <button type="button" className="ghost-btn" onClick={onLogout}>
          ログアウト
        </button>
      </div>
    </header>
  )
}
