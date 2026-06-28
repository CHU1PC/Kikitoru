import { useEffect, useState } from "react"
import "./App.css"
import { UploadForm } from "./components/UploadForm"
import { SummaryView } from "./components/SummaryView"
import { AppHeader } from "./components/AppHeader"
import { LoginScreen } from "./components/LoginScreen"
import { AccessNotice } from "./components/AccessNotice"
import { AdminUsers } from "./components/AdminUsers"
import { Spinner } from "./components/Spinner"
import type { SummaryResponse, UserPublic } from "./gen/types"
import { getMe, logout , startGoogleLogin} from "./api/client"




function App() {
  const [user, setUser] = useState<UserPublic | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)
  const [view, setView] = useState<"main" | "admin">("main")

  useEffect(() => {
    getMe().then(setUser).catch(() => setUser(null)).finally(() => setAuthLoading(false))
  }, [])

  async function handleLogout() {
    await logout()
    setUser(null)
  }

  if (authLoading)
    return (
      <main className="auth-screen">
        <Spinner />
      </main>
    )
  if(!user) return <LoginScreen onLogin={startGoogleLogin} />
  if(user.status != "approved") return <AccessNotice status={user.status} onLogout={handleLogout} />

  return (
    <main className="app">
      <AppHeader user={user} onLogout={handleLogout} view={view} onChangeView={setView} />
      {view === "admin" && user.role === "admin" ? (
        <AdminUsers currentUserId={user.id} />
      ) : (
        <>
          <p className="lead">会議の音声 / 動画をアップロードすると議事録を作成します</p>
          <UploadForm onSuccess={setSummary} />
          {summary && <SummaryView summary={summary} />}
        </>
      )}
    </main>
  )
}

export default App
