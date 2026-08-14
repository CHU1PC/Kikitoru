import type { UserPublic, UserStatusKey } from "../gen/types"
import { Spinner } from "./Spinner"

type StatusFilter = UserStatusKey | "all"

type Props = {
  users: UserPublic[]
  loading: boolean
  statusFilter: StatusFilter
  onStatusFilterChange: (filter: StatusFilter) => void
  onApprove: (userId: string) => void
  onReject: (userId: string) => void
  currentUserId: string
  busyUserId?: string | null
}

const FILTERS: { key: StatusFilter; label: string }[] = [
  { key: "pending", label: "承認待ち" },
  { key: "approved", label: "承認済み" },
  { key: "rejected", label: "却下" },
  { key: "all", label: "すべて" },
]

const STATUS_LABEL: Record<UserStatusKey, string> = {
  pending: "承認待ち",
  approved: "承認済み",
  rejected: "却下",
}

export function AdminPanel({
  users,
  loading,
  statusFilter,
  onStatusFilterChange,
  onApprove,
  onReject,
  currentUserId,
  busyUserId,
}: Props) {
  return (
    <section className="admin">
      <h2 className="admin-title">ユーザー管理</h2>

      <div className="admin-filters">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            className={`admin-filter${statusFilter === f.key ? " active" : ""}`}
            onClick={() => onStatusFilterChange(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner label="読み込み中..." />
      ) : users.length === 0 ? (
        <p className="admin-empty">該当するユーザーはいません。</p>
      ) : (
        <ul className="admin-list">
          {users.map((u) => (
            <li key={u.id} className="admin-row">
              <div className="admin-user">
                <span className="admin-name">{u.name || u.email || "(名前なし)"}</span>
                {u.name && u.email && <span className="admin-email">{u.email}</span>}
              </div>
              <div className="admin-badges">
                {u.role === "admin" && <span className="role-badge">admin</span>}
                <span className={`status-badge status-${u.status}`}>
                  {STATUS_LABEL[u.status]}
                </span>
              </div>
              <div className="admin-actions">
                {u.id === currentUserId ? (
                  <span className="admin-self">自分</span>
                ) : (
                  <>
                    {u.status !== "approved" && (
                      <button
                        type="button"
                        className="approve-btn"
                        disabled={busyUserId === u.id}
                        onClick={() => onApprove(u.id)}
                      >
                        承認
                      </button>
                    )}
                    {u.status !== "rejected" && (
                      <button
                        type="button"
                        className="reject-btn"
                        disabled={busyUserId === u.id}
                        onClick={() => onReject(u.id)}
                      >
                        却下
                      </button>
                    )}
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
