import os
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.application.document_registration import TextDocumentRegistrationPipeline
from app.core.config import Settings
from app.infrastructure.database import create_mysql_connection
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.repositories.mysql_document import MySQLDocumentRepository

RUN_MYSQL_INTEGRATION_TESTS = (
    os.getenv(
        "RUN_MYSQL_INTEGRATION_TESTS",
        "",
    ).lower()
    == "true"
)

pytestmark = pytest.mark.skipif(
    not RUN_MYSQL_INTEGRATION_TESTS,
    reason="RUN_MYSQL_INTEGRATION_TESTS=true일 때만 실행합니다.",
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


def test_register_s3_text_document_in_local_mysql() -> None:
    settings = Settings()
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
    )

    unique_suffix = uuid4().hex
    object_key = f"integration-tests/{unique_suffix}/financial_textbook.txt"
    version_id = f"integration-version-{unique_suffix}"
    stored_content = (
        "예금은 금융기관에 돈을 맡기는 상품이다.\n\n"
        "채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다."
    ).encode()

    document_id: int | None = None

    try:
        with (
            patch(
                "app.application.document_registration.upload_text_object",
                return_value=version_id,
            ) as upload_mock,
            patch(
                "app.application.document_registration.download_text_object",
                return_value=stored_content,
            ) as download_mock,
        ):
            document_id, chunk_count = pipeline.register(
                content=stored_content,
                object_key=object_key,
                document_type="textbook",
                category="integration-test",
                title="금융 교과서 통합 테스트",
                original_filename="financial_textbook.txt",
                publisher="FirstFolio",
            )

        stored_document = document_repository.find_by_id(document_id)
        stored_chunks = chunk_repository.find_by_chunk_keys(
            [
                f"{document_id}:0",
                f"{document_id}:1",
            ]
        )

        assert chunk_count == 2
        assert stored_document.document_id == document_id
        assert stored_document.s3_object_key == object_key
        assert stored_document.s3_version_id == version_id
        assert stored_document.status == "pending"
        assert [chunk.chunk_key for chunk in stored_chunks] == [
            f"{document_id}:0",
            f"{document_id}:1",
        ]
        assert [chunk.content for chunk in stored_chunks] == [
            "예금은 금융기관에 돈을 맡기는 상품이다.",
            "채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다.",
        ]

        upload_mock.assert_called_once_with(
            settings=settings,
            object_key=object_key,
            content=stored_content,
        )
        download_mock.assert_called_once_with(
            settings=settings,
            object_key=object_key,
            version_id=version_id,
        )
    finally:
        if document_id is not None:
            _delete_test_document(
                settings,
                document_id,
            )

    if document_id is None:
        raise RuntimeError("통합 테스트 document_id가 생성되지 않았습니다.")

    assert _count_document_rows(
        settings,
        document_id,
    ) == (0, 0)
