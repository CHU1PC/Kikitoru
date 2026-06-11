import os
from pathlib import Path

import pytest
import torch
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load the real HF_TOKEN from the project .env (needed to download / load the
# pyannote pipeline), then fill in placeholder values for the settings the STT
# path never touches. `app.settings.config` instantiates a single `Settings()`
# at import time that requires DB / OAuth / LLM config, so importing any app.stt
# module would fail without these. Unlike tests/unit/conftest.py, this subtree
# does NOT mock torch / faster_whisper / pyannote -- the real models run here.
load_dotenv(_PROJECT_ROOT / ".env")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://unused:unused@localhost/unused")
os.environ.setdefault("GOOGLE_API_KEY", "unused")
os.environ.setdefault("GOOGLE_CLIENT_ID", "unused")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "unused")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost/unused")
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "30")


@pytest.fixture(scope="module", autouse=True)
def require_gpu_and_token() -> None:
    """GPU と HF_TOKEN の両方がない場合は、モジュール全体のテストをスキップする fixture."""
    if not torch.cuda.is_available():
        pytest.skip("integration test requires a CUDA GPU")
    if not os.environ.get("HF_TOKEN"):
        pytest.skip("integration test requires a real HF_TOKEN (set it in the project .env)")
