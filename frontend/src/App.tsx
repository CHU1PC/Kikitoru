import { useEffect, useState } from "react"
import "./App.css"
import { UploadForm } from "./components/UploadForm"
import { SummaryView } from "./components/SummaryView"
import { AppHeader } from "./components/AppHeader"
import { LoginScreen } from "./components/LoginScreen"
import { AccessNotice } from "./components/AccessNotice"
import type { SummaryResponse, UserPublic } from "./gen/types"
import { getMe, logout , startGoogleLogin} from "./api/client"




function App() {
  const [user, setUser] = useState<UserPublic | null>(null)
  const [authLoading, setAuthLoading] = useState(true)
  const [summary, setSummary] = useState<SummaryResponse | null>(null)

  useEffect(() => {
    getMe().then(setUser).catch(() => setUser(null)).finally(() => setAuthLoading(false))
  }, [])

  async function handleLogout() {
    await logout()
    setUser(null)
  }

  if (authLoading) return null
  if(!user) return <LoginScreen onLogin={startGoogleLogin} />
  if(user.status != "approved") return <AccessNotice status={user.status} onLogout={handleLogout} />

  return (
    <main className="app">
      <AppHeader user={user} onLogout={handleLogout} />
      <p className="lead">会議の音声をアップロードすると議事録を作成します</p>
      <UploadForm onSuccess={setSummary} />
      {summary && <SummaryView summary={summary} />}
    </main>
  )
}

export default App
