from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.router.audio import router as audio_router
from app.router.summaries import router as summaries_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(audio_router)
app.include_router(summaries_router)
