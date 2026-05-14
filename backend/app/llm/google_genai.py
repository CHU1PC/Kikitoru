from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

from app.settings.config import settings

MAX_RETRY = 3

rate_limiter = InMemoryRateLimiter(
    requests_per_second=40,
    check_every_n_seconds=0.1,
    max_bucket_size=80,
)

gemini_2_5_flash = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    api_key=settings.GOOGLE_API_KEY,
    thinking_budget=1024,
    temperature=0,
    max_output_tokens=4096,
    timeout=settings.LLM_TIMEOUT_SECONDS,
    max_retries=MAX_RETRY,
    rate_limiter=rate_limiter,
)

gemini_3_flash = ChatGoogleGenerativeAI(
    model="gemini-3-flash-preview",
    api_key=settings.GOOGLE_API_KEY,
    thinking_budget=1024,
    temperature=0,
    max_output_tokens=4096,
    timeout=settings.LLM_TIMEOUT_SECONDS,
    max_retries=0,
    rate_limiter=rate_limiter,
)


gemini = gemini_3_flash.with_fallbacks([gemini_2_5_flash])
