"""Quick transcription accuracy check. Usage: uv run python scripts/check_transcribe.py <audio_file>"""

import sys
import time
from pathlib import Path

from app.stt.transcribe import transcribe


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <audio_file>")
        sys.exit(1)

    audio = Path(sys.argv[1])
    if not audio.exists():
        print(f"File not found: {audio}")
        sys.exit(1)

    print(f"Transcribing: {audio.name}")
    start = time.perf_counter()
    segments = transcribe(audio)
    elapsed = time.perf_counter() - start

    print(f"\n--- Result ({len(segments)} segments, {elapsed:.1f}s) ---")
    for seg in segments:
        print(f"[{seg.start:6.2f} - {seg.end:6.2f}]  {seg.text}")


if __name__ == "__main__":
    main()
