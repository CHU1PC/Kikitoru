"""Quick transcription accuracy check. Usage: uv run python scripts/check_transcribe.py <audio_file>"""

import sys
import time
from pathlib import Path

import numpy as np
import torchaudio
import torchaudio.functional as F

from app.stt.transcribe import transcribe

_WHISPER_SAMPLE_RATE = 16000


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <audio_file>")
        sys.exit(1)

    audio = Path(sys.argv[1])
    if not audio.exists():
        print(f"File not found: {audio}")
        sys.exit(1)

    waveform, sample_rate = torchaudio.load(str(audio))
    if sample_rate != _WHISPER_SAMPLE_RATE:
        waveform = F.resample(waveform, sample_rate, _WHISPER_SAMPLE_RATE)
    audio_np: np.ndarray = waveform.mean(dim=0).numpy().astype(np.float32)

    print(f"Transcribing: {audio.name}")
    start = time.perf_counter()
    segments = transcribe(audio_np)
    elapsed = time.perf_counter() - start

    print(f"\n--- Result ({len(segments)} segments, {elapsed:.1f}s) ---")
    for seg in segments:
        print(f"[{seg.start:6.2f} - {seg.end:6.2f}]  {seg.text}")


if __name__ == "__main__":
    main()
