import { useState } from "react"
import { AppHeader } from "./AppHeader"
import { Sidebar } from "./Sidebar"
import { UploadForm } from "./UploadForm"
import { SummaryView } from "./SummaryView"
import { AdminUsers } from "./AdminUsers"
import { useSummaries } from "../hooks/useSummaries"
import type { UserPublic } from "../gen/types"

type Props = {
    user: UserPublic
    onLogout: () => void
}

export function Workspace({ user, onLogout }: Props) {
    const [view, setView] = useState<"main" | "admin">("main")
    const { items, listLoading, listError, activeId, detail, select, startNew, addUploaded, reloadList } =
        useSummaries()

    const isAdmin = view === "admin" && user.role === "admin"

    return (
        <div className="appwrap">
            <div className="appwin">
                <AppHeader
                    user={user}
                    onLogout={onLogout}
                    view={view}
                    onChangeView={setView}
                />
                <div className="appbody">
                    {!isAdmin && (
                        <Sidebar
                            items={items}
                            activeId={activeId}
                            loading={listLoading}
                            error={listError}
                            onSelect={select}
                            onNew={startNew}
                            onRetry={reloadList}
                        />
                    )}
                    <main className="main">
                        <div className="main-inner">
                            {isAdmin ? (
                                <AdminUsers currentUserId={user.id} />
                            ) : detail ? (
                                <SummaryView summary={detail} />
                            ) : (
                                <UploadForm onSuccess={addUploaded} />
                            )}
                        </div>
                    </main>
                </div>
            </div>
        </div>
    )
}
