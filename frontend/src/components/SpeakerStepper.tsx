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
            />
            <button type="button" className="step-btn" onClick={() => step(1)}>
                +
            </button>
        </div>
    )
}