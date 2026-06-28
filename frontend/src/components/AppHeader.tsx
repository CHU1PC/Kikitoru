import type { UserPublic } from "../gen/types"
import { Logo } from "./Logo"

type Props = {
  user: UserPublic
  onLogout: () => void
}

export function AppHeader({ user, onLogout }: Props) {
  return (
    <header className="app-header">
      <div className="app-header-brand">
        <Logo size={26} />
        <h1 className="app-header-title">Kikitoru</h1>
      </div>
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
