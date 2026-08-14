import os
from pathlib import Path

from dotenv import load_dotenv

# db/ (実 DB・CI 対象) で共有する env のみをここに置く.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

load_dotenv(_PROJECT_ROOT / ".env")

# .env の実バケットと実キーが載るので, AWS へ出られないよう上書きする.
os.environ["S3_BUCKET"] = "unused"
os.environ["AWS_ACCESS_KEY_ID"] = "unused"
os.environ["AWS_SECRET_ACCESS_KEY"] = "unused"  # ruff:ignore[hardcoded-password-string]
os.environ["AWS_ENDPOINT_URL"] = "http://127.0.0.1:1"

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")
os.environ.setdefault("GOOGLE_API_KEY", "unused")
os.environ.setdefault("GOOGLE_CLIENT_ID", "unused")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "unused")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost/unused")
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "30")
