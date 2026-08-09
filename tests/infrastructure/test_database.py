from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.database import (
    check_mysql_connection,
    create_mysql_connection,
)


@patch("app.infrastructure.database.mysql.connector.connect")
def test_create_mysql_connection_with_settings(
    connect_mock: Mock,
) -> None:
    connection = Mock()
    connect_mock.return_value = connection
    settings = Settings(
        mysql_host="mysql-test",
        mysql_port=3307,
        mysql_database="firstfolio_ai_test",
        mysql_user="test-user",
        mysql_password="test-password",
        _env_file=None,
    )

    result = create_mysql_connection(settings)

    assert result is connection
    connect_mock.assert_called_once_with(
        host="mysql-test",
        port=3307,
        database="firstfolio_ai_test",
        user="test-user",
        password="test-password",
        time_zone="+00:00",
        autocommit=False,
    )


@patch("app.infrastructure.database.mysql.connector.connect")
def test_reject_empty_mysql_password(
    connect_mock: Mock,
) -> None:
    settings = Settings(
        mysql_password="",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="MYSQL_PASSWORD",
    ):
        create_mysql_connection(settings)

    connect_mock.assert_not_called()


@patch("app.infrastructure.database.create_mysql_connection")
def test_check_mysql_connection(
    create_connection_mock: Mock,
) -> None:
    cursor = Mock()
    cursor.fetchone.return_value = (1,)

    connection = Mock()
    connection.cursor.return_value = cursor
    create_connection_mock.return_value = connection

    settings = Settings(
        mysql_password="test-password",
        _env_file=None,
    )

    connected = check_mysql_connection(settings)

    assert connected is True
    cursor.execute.assert_called_once_with("SELECT 1")
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.database.create_mysql_connection")
def test_close_mysql_resources_when_connection_check_fails(
    create_connection_mock: Mock,
) -> None:
    cursor = Mock()
    cursor.execute.side_effect = RuntimeError("database unavailable")

    connection = Mock()
    connection.cursor.return_value = cursor
    create_connection_mock.return_value = connection

    settings = Settings(
        mysql_password="test-password",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="database unavailable",
    ):
        check_mysql_connection(settings)

    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()
