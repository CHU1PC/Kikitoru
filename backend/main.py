from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.router.audio import router as audio_router
from app.router.summaries import router as summaries_router
from app.settings.config import settings

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audio_router)
app.include_router(summaries_router)
