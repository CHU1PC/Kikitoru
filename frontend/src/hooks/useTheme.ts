import { useCallback, useState } from "react"

type Theme = "light" | "dark"

function currentTheme(): Theme {
    return document.documentElement.dataset.theme === "light" ? "light" : "dark"
}

export function useTheme() {
    const [theme, setThemeState] = useState<Theme>(currentTheme)

    const setTheme = useCallback((next: Theme) => {
        document.documentElement.dataset.theme = next
        try {
            localStorage.setItem("kikitoru-theme", next)
        } catch {
            // localStorage が使えない環境では無視する
        }
        setThemeState(next)
    }, [])

    const toggle = useCallback(() => {
        setTheme(theme === "light" ? "dark" : "light")
    }, [theme, setTheme])

    return { theme, toggle }
}