from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from mysql.connector import Error

from app.main import app

client = TestClient(app)


def test_get_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.api.health.check_mysql_connection")
def test_get_database_health(
    check_connection_mock: Mock,
) -> None:
    check_connection_mock.return_value = True

    response = client.get("/health/database")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
    }
    check_connection_mock.assert_called_once_with(app.state.settings)


@patch("app.api.health.check_mysql_connection")
def test_return_service_unavailable_when_database_is_disconnected(
    check_connection_mock: Mock,
) -> None:
    check_connection_mock.return_value = False

    response = client.get("/health/database")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "MySQL 연결을 확인할 수 없습니다.",
    }


@patch("app.api.health.check_mysql_connection")
def test_hide_database_error_details(
    check_connection_mock: Mock,
) -> None:
    check_connection_mock.side_effect = Error(
        "connection failed with sensitive details"
    )

    response = client.get("/health/database")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "MySQL 연결을 확인할 수 없습니다.",
    }
    assert "sensitive details" not in response.text
