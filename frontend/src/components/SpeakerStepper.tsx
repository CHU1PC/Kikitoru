type Props = {
    value: string
    onChange: (value: string) => void
    min?: number
    max?: number
}



export function SpeakerStepper({ value, onChange, min = 1, max = 10 }: Props) {
    function step(delta: number) {
        const current = value === "" ? min : Number(value)
        const next = Math.min(max, Math.max(min, current + delta))
        onChange(String(next))
    }

    function clampInput(raw: string) {
        if (raw === "") {
            onChange(String(min))
            return
        }
        const n = Math.floor(Number(raw))
        if (Number.isNaN(n)) {
            onChange(String(min))
            return
        }
        onChange(String(Math.min(max, Math.max(min, n))))
    }

    return (
        <div className="stepper">
            <button type="button" className="step-btn" onClick={() => step(-1)}>
                -
            </button>
            <input
                className="step-input num"
                type="number"
                min={min}
                max={max}
                value={value}
                onChange={(e) => onChange(e.target.value)}
                onBlur={(e) => clampInput(e.target.value)}
            />
            <button type="button" className="step-btn" onClick={() => step(1)}>
                +
            </button>
        </div>
    )
}