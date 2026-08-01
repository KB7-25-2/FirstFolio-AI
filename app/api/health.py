from fastapi import APIRouter, HTTPException, Request, status
from mysql.connector import Error

from app.infrastructure.database import check_mysql_connection

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/database")
def get_database_health(
    request: Request,
) -> dict[str, str]:
    try:
        connected = check_mysql_connection(request.app.state.settings)
    except (Error, ValueError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL 연결을 확인할 수 없습니다.",
        ) from None

    if not connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MySQL 연결을 확인할 수 없습니다.",
        )

    return {
        "status": "ok",
        "database": "connected",
    }
