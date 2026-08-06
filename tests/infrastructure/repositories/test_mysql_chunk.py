import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from app.application.ports.chunk_repository import ChunkNotFoundError
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository


def _settings() -> Settings:
    return Settings(
        mysql_password="test-password",
        _env_file=None,
    )


def _chunk(
    document_id: str = "12",
    sequence: int = 0,
    heading: str | None = None,
    metadata: dict[str, str] | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_key=f"{document_id}:{sequence}",
        sequence=sequence,
        content=f"청크 본문 {sequence}",
        title="금융 교과서",
        source="financial_textbook.txt",
        heading=heading,
        metadata=metadata,
    )


def _connection_and_cursor() -> tuple[Mock, Mock]:
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    return connection, cursor


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_save_all_commits_chunks(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())
    chunks = [
        _chunk(sequence=0, heading="저축과 저축 상품"),
        _chunk(sequence=1, heading="저축과 저축 상품"),
    ]

    repository.save_all(chunks)

    sql, rows = cursor.executemany.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "INSERT INTO AI_DOCUMENT_CHUNKS" in normalized_sql
    assert "heading" in normalized_sql
    assert [row[:-1] for row in rows] == [
        (12, "12:0", 0, "paragraph", "저축과 저축 상품", "청크 본문 0"),
        (12, "12:1", 1, "paragraph", "저축과 저축 상품", "청크 본문 1"),
    ]
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_save_all_does_not_connect_when_chunks_are_empty(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLChunkRepository(_settings())

    repository.save_all([])

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_replace_document_chunks_deletes_and_inserts_in_one_transaction(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())
    chunks = [
        _chunk(sequence=0, heading="저축과 저축 상품"),
        _chunk(sequence=1, heading="저축과 저축 상품"),
    ]

    repository.replace_document_chunks(
        document_id="12",
        chunks=chunks,
    )

    delete_sql, delete_parameters = cursor.execute.call_args.args
    normalized_delete_sql = " ".join(delete_sql.split())
    insert_sql, rows = cursor.executemany.call_args.args
    normalized_insert_sql = " ".join(insert_sql.split())

    assert "DELETE FROM AI_DOCUMENT_CHUNKS" in normalized_delete_sql
    assert delete_parameters == (12,)
    assert "INSERT INTO AI_DOCUMENT_CHUNKS" in normalized_insert_sql
    assert "heading" in normalized_insert_sql
    assert [row[:-1] for row in rows] == [
        (12, "12:0", 0, "paragraph", "저축과 저축 상품", "청크 본문 0"),
        (12, "12:1", 1, "paragraph", "저축과 저축 상품", "청크 본문 1"),
    ]
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_replace_document_chunks_allows_removing_all_chunks(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    repository.replace_document_chunks(
        document_id="12",
        chunks=[],
    )

    _, delete_parameters = cursor.execute.call_args.args

    assert delete_parameters == (12,)
    cursor.executemany.assert_not_called()
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_replace_document_chunks_rolls_back_when_insert_fails(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.executemany.side_effect = RuntimeError("insert failed")
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    with pytest.raises(
        RuntimeError,
        match="insert failed",
    ):
        repository.replace_document_chunks(
            document_id="12",
            chunks=[_chunk()],
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_replace_chunks_with_shared_connection_does_not_finish_transaction(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    repository = MySQLChunkRepository(_settings())

    repository.replace_document_chunks_in_transaction(
        connection=connection,
        document_id="12",
        chunks=[
            _chunk(sequence=0, heading="저축과 저축 상품"),
            _chunk(sequence=1, heading="저축과 저축 상품"),
        ],
    )

    delete_sql, delete_parameters = cursor.execute.call_args.args
    insert_sql, rows = cursor.executemany.call_args.args

    assert "DELETE FROM AI_DOCUMENT_CHUNKS" in " ".join(delete_sql.split())
    assert delete_parameters == (12,)
    assert "INSERT INTO AI_DOCUMENT_CHUNKS" in " ".join(insert_sql.split())
    assert [row[:-1] for row in rows] == [
        (12, "12:0", 0, "paragraph", "저축과 저축 상품", "청크 본문 0"),
        (12, "12:1", 1, "paragraph", "저축과 저축 상품", "청크 본문 1"),
    ]

    create_connection_mock.assert_not_called()
    connection.commit.assert_not_called()
    connection.rollback.assert_not_called()
    connection.close.assert_not_called()
    cursor.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_find_all_returns_chunks(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = [
        (
            12,
            "12:0",
            0,
            "첫 번째 본문",
            "금융 교과서",
            "financial_textbook.txt",
            "저축과 저축 상품",
            None,
            None,
        ),
        (
            12,
            "12:1",
            1,
            "두 번째 본문",
            "금융 교과서",
            "https://example.com/textbook",
            None,
            "https://example.com/textbook",
            datetime(2026, 8, 3, 9, 0),
        ),
    ]
    cursor.fetchall.return_value = [
        row + (None,) for row in cursor.fetchall.return_value
    ]
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    chunks = repository.find_all()

    sql = cursor.execute.call_args.args[0]
    normalized_sql = " ".join(sql.split())

    assert "INNER JOIN AI_DOCUMENTS" in normalized_sql
    assert "ORDER BY chunks.document_id, chunks.chunk_order" in normalized_sql
    assert chunks == [
        DocumentChunk(
            document_id="12",
            chunk_key="12:0",
            sequence=0,
            content="첫 번째 본문",
            title="금융 교과서",
            source="financial_textbook.txt",
            heading="저축과 저축 상품",
        ),
        DocumentChunk(
            document_id="12",
            chunk_key="12:1",
            sequence=1,
            content="두 번째 본문",
            title="금융 교과서",
            source="https://example.com/textbook",
            source_url="https://example.com/textbook",
            published_at=datetime(2026, 8, 3, 9, 0),
        ),
    ]
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_find_by_chunk_keys_preserves_requested_order(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = [
        (
            12,
            "12:1",
            1,
            "두 번째 본문",
            "금융 교과서",
            "financial_textbook.txt",
            "저축과 저축 상품",
            None,
            None,
        ),
        (
            12,
            "12:0",
            0,
            "첫 번째 본문",
            "금융 교과서",
            "financial_textbook.txt",
            None,
            None,
            None,
        ),
    ]
    cursor.fetchall.return_value = [
        row + (None,) for row in cursor.fetchall.return_value
    ]
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    chunks = repository.find_by_chunk_keys(
        ["12:0", "12:1"],
    )

    _, parameters = cursor.execute.call_args.args

    assert parameters == ("12:0", "12:1")
    assert [chunk.chunk_key for chunk in chunks] == [
        "12:0",
        "12:1",
    ]
    assert [chunk.heading for chunk in chunks] == [
        None,
        "저축과 저축 상품",
    ]
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_find_by_chunk_keys_raises_when_key_is_missing(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = [
        (
            12,
            "12:0",
            0,
            "첫 번째 본문",
            "금융 교과서",
            "financial_textbook.txt",
            None,
            None,
            None,
        )
    ]
    cursor.fetchall.return_value = [
        row + (None,) for row in cursor.fetchall.return_value
    ]
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    with pytest.raises(
        ChunkNotFoundError,
        match="12:1",
    ):
        repository.find_by_chunk_keys(
            ["12:0", "12:1"],
        )

    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_find_by_chunk_keys_does_not_connect_for_empty_keys(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLChunkRepository(_settings())

    chunks = repository.find_by_chunk_keys([])

    assert chunks == []
    create_connection_mock.assert_not_called()


@pytest.mark.parametrize(
    "document_id",
    [
        "document-001",
        "01",
        "0",
        "-1",
    ],
)
@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_rejects_invalid_mysql_document_id(
    create_connection_mock: Mock,
    document_id: str,
) -> None:
    repository = MySQLChunkRepository(_settings())

    with pytest.raises(
        ValueError,
        match="양의 정수 문자열",
    ):
        repository.replace_document_chunks(
            document_id=document_id,
            chunks=[],
        )

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_rejects_chunk_from_another_document(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLChunkRepository(_settings())

    with pytest.raises(
        ValueError,
        match="document_id",
    ):
        repository.replace_document_chunks(
            document_id="12",
            chunks=[_chunk(document_id="13")],
        )

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_rejects_invalid_chunk_key(
    create_connection_mock: Mock,
) -> None:
    repository = MySQLChunkRepository(_settings())
    chunk = DocumentChunk(
        document_id="12",
        chunk_key="incorrect-key",
        sequence=0,
        content="청크 본문",
        title="금융 교과서",
        source="financial_textbook.txt",
    )

    with pytest.raises(
        ValueError,
        match="chunk_key",
    ):
        repository.save_all([chunk])

    create_connection_mock.assert_not_called()


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_save_all_serializes_chunk_metadata(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())
    metadata = {
        "chapter_heading": "Savings",
        "section_heading": "Income",
    }

    repository.save_all([_chunk(metadata=metadata)])

    sql, rows = cursor.executemany.call_args.args
    normalized_sql = " ".join(sql.split())

    assert "metadata_json" in normalized_sql
    assert json.loads(rows[0][-1]) == metadata


@patch("app.infrastructure.repositories.mysql_chunk.create_mysql_connection")
def test_find_by_chunk_keys_restores_chunk_metadata(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    cursor.fetchall.return_value = [
        (
            12,
            "12:0",
            0,
            "Chunk body",
            "Financial Textbook",
            "financial_textbook.txt",
            "Income",
            None,
            None,
            '{"chapter_heading": "Savings", "section_heading": "Income"}',
        )
    ]
    create_connection_mock.return_value = connection
    repository = MySQLChunkRepository(_settings())

    chunks = repository.find_by_chunk_keys(["12:0"])

    sql = cursor.execute.call_args.args[0]
    assert "chunks.metadata_json" in " ".join(sql.split())
    assert chunks[0].metadata == {
        "chapter_heading": "Savings",
        "section_heading": "Income",
    }
