import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("HF_TOKEN", "test_hf_token")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

sys.modules.update({
    "torch": MagicMock(),
    "torchaudio": MagicMock(),
    "torchaudio.functional": MagicMock(),
    "faster_whisper": MagicMock(),
    "pyannote": MagicMock(),
    "pyannote.audio": MagicMock(),
})
