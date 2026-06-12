import os
from pathlib import Path

import pytest
import torch
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(_PROJECT_ROOT / ".env")
os.environ.setdefault("HF_TOKEN", "")
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
