from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.rate_limit import limiter, rate_limit_exceeded_handler
from app.router.admin import router as admin_router
from app.router.audio import router as audio_router
from app.router.oauth import oauth_router
from app.router.summaries import summaries_router
from app.settings import settings

app = FastAPI(
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(audio_router, prefix="/api/v1")
app.include_router(summaries_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(oauth_router)
