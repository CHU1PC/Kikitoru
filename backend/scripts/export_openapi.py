import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

BACKEND = Path(__file__).resolve().parent.parent   # scripts/ の親 = backend/
sys.path.insert(0, str(BACKEND))
sys.modules.update({
    "torch": MagicMock(),
    "torchaudio": MagicMock(),
    "torchaudio.functional": MagicMock(),
    "faster_whisper": MagicMock(),
    "pyannote": MagicMock(),
    "pyannote.audio": MagicMock(),
})

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
os.environ.setdefault("HF_TOKEN", "dummy")
os.environ.setdefault("GOOGLE_API_KEY", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_ID", "dummy")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "dummy")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google")

from main import app  # noqa: E402

out = Path(__file__).parents[1] / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
