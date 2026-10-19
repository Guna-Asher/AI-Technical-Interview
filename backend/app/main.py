from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, interviews
from app.config import get_settings

settings = get_settings()

app = FastAPI(title="AI Technical Interview API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(interviews.router, prefix="/api")
