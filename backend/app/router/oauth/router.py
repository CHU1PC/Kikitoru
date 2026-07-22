from fastapi import APIRouter

from app.router.oauth.google import router as google_router
from app.router.oauth.session import router as session_router

# 各 IdP (google / 将来 github, apple) のルータと provider 非依存の認証
# エンドポイント (session) を /auth 配下に束ねる親ルータ.
oauth_router = APIRouter(prefix="/auth", tags=["auth"])
oauth_router.include_router(google_router)
oauth_router.include_router(session_router)
