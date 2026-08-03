import os
from uuid import uuid4

import pytest
from mysql.connector import Error

from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.document import DocumentMetadata
from app.infrastructure.database import create_mysql_connection
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.repositories.mysql_document import MySQLDocumentRepository

RUN_MYSQL_INTEGRATION_TESTS = (
    os.getenv("RUN_MYSQL_INTEGRATION_TESTS", "").lower() == "true"
)

pytestmark = pytest.mark.skipif(
    not RUN_MYSQL_INTEGRATION_TESTS,
    reason="RUN_MYSQL_INTEGRATION_TESTS=true일 때만 실행합니다.",
)


def _document(unique_suffix: str) -> DocumentMetadata:
    return DocumentMetadata(
        document_type="textbook",
        category="integration-test",
        title=f"MySQL 통합 테스트 문서 {unique_suffix}",
        original_filename="financial_textbook.txt",
        content_type="text/plain",
        s3_object_key=f"integration-tests/{unique_suffix}/financial_textbook.txt",
        s3_version_id=f"integration-version-{unique_suffix}",
        status="pending",
    )


def _chunk(
    document_id: int,
    sequence: int,
) -> DocumentChunk:
    string_document_id = str(document_id)

    return DocumentChunk(
        document_id=string_document_id,
        chunk_key=f"{string_document_id}:{sequence}",
        sequence=sequence,
        content=f"MySQL 통합 테스트 청크 {sequence}",
        title="MySQL 통합 테스트 문서",
        source="financial_textbook.txt",
    )


def _count_document_rows(
    settings: Settings,
    document_id: int,
) -> tuple[int, int]:
    connection = create_mysql_connection(settings)

    try:
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM AI_DOCUMENTS
                        WHERE document_id = %s
                    ),
                    (
                        SELECT COUNT(*)
                        FROM AI_DOCUMENT_CHUNKS
                        WHERE document_id = %s
                    )
                """,
                (document_id, document_id),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        connection.close()

    if row is None:
        raise RuntimeError("통합 테스트 데이터 개수를 조회할 수 없습니다.")

    return int(row[0]), int(row[1])


def _delete_test_document(
    settings: Settings,
    document_id: int,
) -> None:
    connection = create_mysql_connection(settings)

    try:
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                DELETE FROM AI_DOCUMENTS
                WHERE document_id = %s
                """,
                (document_id,),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def test_create_and_read_document_with_chunks() -> None:
    settings = Settings()
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    connection = create_mysql_connection(settings)
    document_id: int | None = None

    try:
        document_id = document_repository.create_in_transaction(
            connection=connection,
            document=_document(uuid4().hex),
        )
        chunks = [
            _chunk(document_id=document_id, sequence=0),
            _chunk(document_id=document_id, sequence=1),
        ]
        chunk_repository.replace_document_chunks_in_transaction(
            connection=connection,
            document_id=str(document_id),
            chunks=chunks,
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    try:
        stored_document = document_repository.find_by_id(document_id)
        stored_chunks = chunk_repository.find_by_chunk_keys(
            [f"{document_id}:0", f"{document_id}:1"]
        )

        assert stored_document.document_id == document_id
        assert stored_document.s3_object_key.startswith("integration-tests/")
        assert stored_document.s3_version_id.startswith("integration-version-")
        assert [chunk.chunk_key for chunk in stored_chunks] == [
            f"{document_id}:0",
            f"{document_id}:1",
        ]
        assert [chunk.content for chunk in stored_chunks] == [
            "MySQL 통합 테스트 청크 0",
            "MySQL 통합 테스트 청크 1",
        ]
    finally:
        _delete_test_document(settings, document_id)

    assert _count_document_rows(settings, document_id) == (0, 0)


def test_rolls_back_document_when_chunk_insert_fails() -> None:
    settings = Settings()
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    connection = create_mysql_connection(settings)
    document_id: int | None = None

    try:
        document_id = document_repository.create_in_transaction(
            connection=connection,
            document=_document(uuid4().hex),
        )
        duplicated_chunk = _chunk(
            document_id=document_id,
            sequence=0,
        )

        with pytest.raises(Error):
            chunk_repository.replace_document_chunks_in_transaction(
                connection=connection,
                document_id=str(document_id),
                chunks=[duplicated_chunk, duplicated_chunk],
            )
    finally:
        connection.rollback()
        connection.close()

    if document_id is None:
        raise RuntimeError("롤백을 확인할 document_id가 생성되지 않았습니다.")

    try:
        assert _count_document_rows(settings, document_id) == (0, 0)
    finally:
        _delete_test_document(settings, document_id)
