import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("GOOGLE_API_KEY", "test-api-key")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GOOGLE_REDIRECT_URI", "http://localhost/auth/callback")
os.environ.setdefault("LLM_TIMEOUT_SECONDS", "30")
