import { useEffect, useState } from "react"
import "./App.css"
import { Workspace } from "./components/Workspace"
import { LoginScreen } from "./components/LoginScreen"
import { AccessNotice } from "./components/AccessNotice"
import { Spinner } from "./components/Spinner"
import type { UserPublic } from "./gen/types"
import { getMe, logout, startGoogleLogin } from "./api/client"

function App() {
    const [user, setUser] = useState<UserPublic | null>(null)
    const [authLoading, setAuthLoading] = useState(true)

    useEffect(() => {
        getMe()
            .then(setUser)
            .catch(() => setUser(null))
            .finally(() => setAuthLoading(false))
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
    if (!user) return <LoginScreen onLogin={startGoogleLogin} />
    if (user.status !== "approved")
        return <AccessNotice status={user.status} onLogout={handleLogout} />

    return <Workspace user={user} onLogout={handleLogout} />
}

export default App
