import { useEffect, useState } from "react"
import { listUsers, updateUser } from "../api/client"
import { AdminPanel } from "./AdminPanel"
import type { UserPublic, UserStatusKey } from "../gen/types"

type StatusFilter = UserStatusKey | "all"

type Props = {
  currentUserId: string
}

export function AdminUsers({ currentUserId }: Props) {
  const [users, setUsers] = useState<UserPublic[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending")
  const [busyUserId, setBusyUserId] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    listUsers(statusFilter === "all" ? undefined : statusFilter)
      .then((rows) => {
        if (active) setUsers(rows)
      })
      .catch(() => {
        if (active) setUsers([])
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [statusFilter])

  function changeFilter(filter: StatusFilter) {
    setLoading(true)
    setStatusFilter(filter)
  }

  async function patch(userId: string, status: UserStatusKey) {
    setBusyUserId(userId)
    try {
      await updateUser(userId, { status })
      const next = await listUsers(statusFilter === "all" ? undefined : statusFilter)
      setUsers(next)
    } finally {
      setBusyUserId(null)
    }
  }

  return (
    <AdminPanel
      users={users}
      loading={loading}
      statusFilter={statusFilter}
      onStatusFilterChange={changeFilter}
      onApprove={(id) => patch(id, "approved")}
      onReject={(id) => patch(id, "rejected")}
      currentUserId={currentUserId}
      busyUserId={busyUserId}
    />
  )
}
