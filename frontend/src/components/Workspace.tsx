import { useState } from "react"
import { AppHeader } from "./AppHeader"
import { Sidebar } from "./Sidebar"
import { UploadForm } from "./UploadForm"
import { SummaryDetail } from "./SummaryDetail"
import { AdminUsers } from "./AdminUsers"
import { useSummaries } from "../hooks/useSummaries"
import { useJobs } from "../hooks/useJobs"
import type { UserPublic } from "../gen/types"

type Props = {
    user: UserPublic
    onLogout: () => void
}

export function Workspace({ user, onLogout }: Props) {
    const [view, setView] = useState<"main" | "admin">("main")
    const { items, listLoading, listError, activeId, detail, select, startNew, reloadList } = useSummaries()
    const { jobs, startUpload } = useJobs((summaryId) => {
        reloadList()
        if (summaryId) select(summaryId) // cache hit なら既存要約を開く
    })
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
                            jobs={jobs}
                        />
                    )}
                    <main className="main">
                        <div className="main-inner">
                            {isAdmin ? (
                                <AdminUsers currentUserId={user.id} />
                            ) : detail ? (
                                <SummaryDetail key={detail.id} summary={detail} />
                            ) : (
                                <UploadForm onStartUpload={startUpload} />
                            )}
                        </div>
                    </main>
                </div>
            </div>
        </div>
    )
}
