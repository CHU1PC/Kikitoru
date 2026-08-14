import type { UserPublic } from "../gen/types"
import { Logo } from "./Logo"
import { useTheme } from "../hooks/useTheme"

type View = "main" | "admin"

type Props = {
    user: UserPublic
    onLogout: () => void
    view?: View
    onChangeView?: (view: View) => void
}

export function AppHeader({ user, onLogout, view = "main", onChangeView }: Props) {
    const { toggle } = useTheme()

    return (
        <header className="appbar">
            <div className="brand">
                <Logo size={22} />
                <span className="brand-name">Kikitoru</span>
            </div>

            <div className="appbar-right">
                {user.role === "admin" && onChangeView && (
                    <nav className="appbar-nav">
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
                <span className="user-name">{user.name || user.email}</span>
                <button
                    type="button"
                    className="ghost"
                    onClick={toggle}
                    aria-label="テーマ切替"
                    title="テーマ切替"
                >
                    ◐
                </button>
                <button type="button" className="ghost" onClick={onLogout}>
                    ログアウト
                </button>
            </div>
        </header>
    )
}
