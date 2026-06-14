from fastapi import APIRouter

from app.router.oauth.google import router as google_router

# 各 IdP (google / 将来 github, apple) のルータを /auth 配下に束ねる親ルータ.
oauth_router = APIRouter(prefix="/auth", tags=["auth"])
oauth_router.include_router(google_router)
