from fastapi import FastAPI

from app.api.dev_quiz_console import router as dev_quiz_console_router
from app.api.dev_quiz_generations import router as dev_quiz_generations_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.quiz_mvp import create_quiz_generation_service

settings = get_settings()

app = FastAPI(title="FirstFolio AI Service")
app.state.settings = settings

app.include_router(health_router)

if settings.app_env == "local":
    app.state.quiz_generation_service = create_quiz_generation_service(settings)
    app.include_router(dev_quiz_generations_router)
    app.include_router(dev_quiz_console_router)
