from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.domain.document import DocumentMetadata
from app.infrastructure.repositories.mysql_document import (
    DocumentNotFoundError,
    MySQLDocumentRepository,
)


def _settings() -> Settings:
    return Settings(
        mysql_password="test-password",
        _env_file=None,
    )


def _document(
    document_id: int | None = None,
    s3_object_key: str = "documents/financial_textbook.txt",
    s3_version_id: str = "version-001",
) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=document_id,
        document_type="textbook",
        category="financial-education",
        title="금융 교과서",
        original_filename="financial_textbook.txt",
        content_type="text/plain",
        s3_object_key=s3_object_key,
        s3_version_id=s3_version_id,
        source_url=None,
        publisher="FirstFolio",
        published_at=datetime(2026, 8, 1, 9, 30),
        status="pending",
        error_message=None,
    )


def _connection_and_cursor() -> tuple[Mock, Mock]:
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor

    return connection, cursor


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_document_commits_and_returns_document_id(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.lastrowid = 12
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())
    document = _document()

    document_id = repository.create(document)

    sql, parameters = cursor.execute.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "INSERT INTO AI_DOCUMENTS" in normalized_sql
    assert parameters == (
        "textbook",
        "financial-education",
        "금융 교과서",
        "financial_textbook.txt",
        "text/plain",
        "documents/financial_textbook.txt",
        "version-001",
        None,
        "FirstFolio",
        datetime(2026, 8, 1, 9, 30),
        "pending",
        None,
    )
    assert document_id == 12
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_document_rolls_back_when_insert_fails(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.execute.side_effect = RuntimeError("insert failed")
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        RuntimeError,
        match="insert failed",
    ):
        repository.create(_document())

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_with_shared_connection_does_not_finish_transaction(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.lastrowid = 12
    repository = MySQLDocumentRepository(_settings())

    document_id = repository.create_in_transaction(
        connection=connection,
        document=_document(),
    )

    assert document_id == 12
    create_connection_mock.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    cursor.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_document_rolls_back_when_document_id_is_missing(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.lastrowid = None
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        RuntimeError,
        match="document_id",
    ):
        repository.create(_document())

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_find_by_id_returns_document_metadata(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    published_at = datetime(2026, 8, 1, 9, 30)
    created_at = datetime(2026, 8, 1, 10, 0)
    updated_at = datetime(2026, 8, 1, 10, 5)
    cursor.fetchone.return_value = (
        12,
        "textbook",
        "financial-education",
        "금융 교과서",
        "financial_textbook.txt",
        "text/plain",
        "documents/financial_textbook.txt",
        "version-001",
        None,
        "FirstFolio",
        published_at,
        "ready",
        None,
        created_at,
        updated_at,
    )
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    document = repository.find_by_id(12)

    sql, parameters = cursor.execute.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "FROM AI_DOCUMENTS" in normalized_sql
    assert parameters == (12,)
    assert document == DocumentMetadata(
        document_id=12,
        document_type="textbook",
        category="financial-education",
        title="금융 교과서",
        original_filename="financial_textbook.txt",
        content_type="text/plain",
        s3_object_key="documents/financial_textbook.txt",
        s3_version_id="version-001",
        source_url=None,
        publisher="FirstFolio",
        published_at=published_at,
        status="ready",
        error_message=None,
        created_at=created_at,
        updated_at=updated_at,
    )
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_find_by_id_raises_when_document_does_not_exist(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchone.return_value = None
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        DocumentNotFoundError,
        match="12",
    ):
        repository.find_by_id(12)

    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_find_by_id_rejects_non_positive_id(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        ValueError,
        match="양의 정수",
    ):
        repository.find_by_id(0)

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_rejects_existing_document_id(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        ValueError,
        match="document_id",
    ):
        repository.create(
            _document(document_id=12),
        )

    create_connection_mock.assert_not_called()


@pytest.mark.parametrize(
    (
        "s3_object_key",
        "s3_version_id",
        "error_message",
    ),
    [
        (
            "",
            "version-001",
            "s3_object_key",
        ),
        (
            "documents/financial_textbook.txt",
            " ",
            "s3_version_id",
        ),
    ],
)
@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_create_rejects_empty_s3_identifier(
    create_connection_mock: Mock,
    s3_object_key: str,
    s3_version_id: str,
    error_message: str,
) -> None:
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        repository.create(
            _document(
                s3_object_key=s3_object_key,
                s3_version_id=s3_version_id,
            )
        )

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_update_document_storage_commits(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 1
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    repository.update_storage(
        document_id=12,
        s3_object_key="documents/financial_textbook.txt",
        s3_version_id="version-002",
        status="pending",
    )

    sql, parameters = cursor.execute.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "UPDATE AI_DOCUMENTS" in normalized_sql
    assert "error_message = NULL" in normalized_sql
    assert parameters == (
        "documents/financial_textbook.txt",
        "version-002",
        "pending",
        12,
    )
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_update_document_storage_with_shared_connection() -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 1
    repository = MySQLDocumentRepository(_settings())

    repository.update_storage_in_transaction(
        connection=connection,
        document_id=12,
        s3_object_key="documents/financial_textbook.txt",
        s3_version_id="version-002",
        status="pending",
    )

    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    cursor.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_delete_document_commits(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 1
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    repository.delete(12)

    sql, parameters = cursor.execute.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "DELETE FROM AI_DOCUMENTS" in normalized_sql
    assert parameters == (12,)
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_delete_document_rolls_back_when_document_is_missing(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 0
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        DocumentNotFoundError,
        match="12",
    ):
        repository.delete(12)

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


def test_delete_with_shared_connection_does_not_finish_transaction() -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 1
    repository = MySQLDocumentRepository(_settings())

    repository.delete_in_transaction(
        connection=connection,
        document_id=12,
    )

    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    cursor.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_delete_rejects_non_positive_id(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        ValueError,
        match="양의 정수",
    ):
        repository.delete(0)

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_document.create_mysql_connection")
def test_update_document_storage_rolls_back_when_document_is_missing(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.rowcount = 0
    create_connection_mock.return_value = connection
    repository = MySQLDocumentRepository(_settings())

    with pytest.raises(
        DocumentNotFoundError,
        match="12",
    ):
        repository.update_storage(
            document_id=12,
            s3_object_key="documents/financial_textbook.txt",
            s3_version_id="version-002",
            status="pending",
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()
