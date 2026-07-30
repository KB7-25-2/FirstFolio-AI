from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title="FirstFolio AI Service")
app.state.settings = settings

app.include_router(health_router)
