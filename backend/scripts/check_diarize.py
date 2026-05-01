"""Quick diarization check. Usage: uv run python scripts/check_diarize.py <audio_file>"""

import sys
import time
from pathlib import Path

from app.stt.diarize import diarize


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <audio_file>")
        sys.exit(1)

    audio = Path(sys.argv[1])
    if not audio.exists():
        print(f"File not found: {audio}")
        sys.exit(1)

    print(f"Diarizing: {audio.name}")
    start = time.perf_counter()
    turns = diarize(audio)
    elapsed = time.perf_counter() - start

    print(f"\n--- Result ({len(turns)} turns, {elapsed:.1f}s) ---")
    for turn in turns:
        print(f"[{turn.start:6.2f} - {turn.end:6.2f}]  {turn.speaker}")


if __name__ == "__main__":
    main()
