from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.router.audio import router as audio_router
from app.router.oauth import oauth_router
from app.router.summaries import router as summaries_router
from app.settings.config import settings

app = FastAPI(
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(audio_router, prefix="/api/v1")
app.include_router(summaries_router, prefix="/api/v1")
app.include_router(oauth_router)
