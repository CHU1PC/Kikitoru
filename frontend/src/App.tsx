import { useState } from "react"
import "./App.css"
import { UploadForm } from "./components/UploadForm"
import { SummaryView } from "./components/SummaryView"
import type { SummaryRead } from "./gen/types"



function App() {
  const [summary, setSummary] = useState<SummaryRead | null>(null)
  return (
    <main className="app">
      <h1>Kikitoru</h1>
      <p className="lead">会議の音声をアップロードすると議事録を作成します</p>
      <UploadForm onSuccess={setSummary} />
      {summary && <SummaryView summary={summary} />}
    </main>
  )
}

export default App
