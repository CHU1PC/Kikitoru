from fastapi import APIRouter

from app.router.summaries.children import router as children_router
from app.router.summaries.core import router as core_router
from app.router.summaries.transcript import router as transcript_router

summaries_router = APIRouter()
summaries_router.include_router(core_router, prefix="/summaries")
summaries_router.include_router(children_router, prefix="/summaries")
summaries_router.include_router(transcript_router, prefix="/summaries")
