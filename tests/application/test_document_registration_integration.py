import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.application.document_registration import TextDocumentRegistrationPipeline
from app.application.search.bm25_pipeline import BM25SearchPipeline
from app.application.search.faiss_pipeline import (
    FaissIndexNotBuiltError,
    FaissSearchPipeline,
)
from app.application.search.hybrid import HybridSearch
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.infrastructure.database import create_mysql_connection
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.repositories.mysql_document import MySQLDocumentRepository
from app.infrastructure.search.bm25 import BM25Search
from app.infrastructure.search.faiss import FaissVectorSearch
from app.infrastructure.tokenizers.kiwi import KiwiTokenizer

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


def test_rebuild_bm25_index_from_mysql_chunks() -> None:
    settings = Settings(
        search_top_k=3,
    )
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    registration_pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
    )

    unique_suffix = uuid4().hex
    unique_search_token = f"bm25mysql{unique_suffix}"
    object_key = f"integration-tests/{unique_suffix}/bm25_financial_textbook.txt"
    version_id = f"integration-version-{unique_suffix}"
    stored_content = (
        f"{unique_search_token} 예금은 금리를 제공한다.\n\n"
        "채권은 만기와 이자를 가진다.\n\n"
        "주식은 기업의 지분을 나타낸다."
    ).encode()

    document_id: int | None = None

    try:
        with (
            patch(
                "app.application.document_registration.upload_text_object",
                return_value=version_id,
            ),
            patch(
                "app.application.document_registration.download_text_object",
                return_value=stored_content,
            ),
        ):
            document_id, chunk_count = registration_pipeline.register(
                content=stored_content,
                object_key=object_key,
                document_type="textbook",
                category="integration-test",
                title="BM25 MySQL 통합 테스트",
                original_filename="bm25_financial_textbook.txt",
                publisher="FirstFolio",
            )

        search_pipeline = BM25SearchPipeline(
            settings=settings,
            chunk_repository=chunk_repository,
        )

        indexed_chunk_count = search_pipeline.rebuild_index()
        results = search_pipeline.search(unique_search_token)

        assert chunk_count == 3
        assert indexed_chunk_count >= 3
        assert len(results) == 1
        assert results[0].chunk.document_id == str(document_id)
        assert results[0].chunk.chunk_key == f"{document_id}:0"
        assert unique_search_token in results[0].chunk.content
        assert results[0].score > 0
    finally:
        if document_id is not None:
            _delete_test_document(
                settings,
                document_id,
            )

    if document_id is None:
        raise RuntimeError("BM25 통합 테스트 document_id가 생성되지 않았습니다.")

    assert _count_document_rows(
        settings,
        document_id,
    ) == (0, 0)


def test_rebuild_faiss_index_after_mysql_chunk_replacement() -> None:
    settings = Settings(
        search_top_k=100,
    )
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    faiss_pipeline = FaissSearchPipeline(
        settings=settings,
        chunk_repository=chunk_repository,
        embedding_client=DeterministicFakeEmbedding(size=8),
    )
    registration_pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        index_invalidator=faiss_pipeline.invalidate_index,
    )

    unique_suffix = uuid4().hex
    object_key = f"integration-tests/{unique_suffix}/faiss_textbook.txt"
    version_id = f"integration-version-{unique_suffix}"
    stored_content = (
        "예금은 금리를 제공한다.\n\n"
        "채권은 만기와 이자를 가진다.\n\n"
        "주식은 기업의 지분을 나타낸다."
    ).encode()
    document_id: int | None = None

    try:
        with (
            patch(
                "app.application.document_registration.upload_text_object",
                return_value=version_id,
            ),
            patch(
                "app.application.document_registration.download_text_object",
                return_value=stored_content,
            ),
        ):
            document_id, chunk_count = registration_pipeline.register(
                content=stored_content,
                object_key=object_key,
                document_type="textbook",
                category="integration-test",
                title="FAISS MySQL 통합 테스트",
                original_filename="faiss_textbook.txt",
                publisher="FirstFolio",
            )

        indexed_chunk_count = faiss_pipeline.rebuild_index()
        initial_results = faiss_pipeline.search("예금은 금리를 제공한다.")
        initial_keys = {result.chunk_key for result in initial_results}

        assert chunk_count == 3
        assert indexed_chunk_count >= 3
        assert f"{document_id}:0" in initial_keys
        assert f"{document_id}:1" in initial_keys
        assert f"{document_id}:2" in initial_keys

        string_document_id = str(document_id)
        chunk_repository.replace_document_chunks(
            document_id=string_document_id,
            chunks=[
                DocumentChunk(
                    document_id=string_document_id,
                    chunk_key=f"{document_id}:0",
                    sequence=0,
                    content="교체 후 예금 설명",
                    title="FAISS MySQL 통합 테스트",
                    source="faiss_textbook.txt",
                )
            ],
        )
        faiss_pipeline.invalidate_index()

        with pytest.raises(
            FaissIndexNotBuiltError,
            match="rebuild_index",
        ):
            faiss_pipeline.search("교체 후 예금 설명")

        reindexed_chunk_count = faiss_pipeline.rebuild_index()
        replaced_results = faiss_pipeline.search("교체 후 예금 설명")
        replaced_keys = {result.chunk_key for result in replaced_results}

        assert reindexed_chunk_count == indexed_chunk_count - 2
        assert f"{document_id}:0" in replaced_keys
        assert f"{document_id}:1" not in replaced_keys
        assert f"{document_id}:2" not in replaced_keys
    finally:
        if document_id is not None:
            _delete_test_document(
                settings,
                document_id,
            )

    if document_id is None:
        raise RuntimeError("FAISS 통합 테스트 document_id가 생성되지 않았습니다.")

    assert _count_document_rows(
        settings,
        document_id,
    ) == (0, 0)


def test_hybrid_search_with_mysql_chunks() -> None:
    settings = Settings(
        search_top_k=3,
        bm25_weight=0.7,
        faiss_weight=0.3,
    )
    document_repository = MySQLDocumentRepository(settings)
    chunk_repository = MySQLChunkRepository(settings)
    registration_pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
    )

    unique_suffix = uuid4().hex
    unique_search_token = f"hybridmysql{unique_suffix}"
    object_key = f"integration-tests/{unique_suffix}/hybrid_textbook.txt"
    version_id = f"integration-version-{unique_suffix}"
    stored_content = (
        f"{unique_search_token} 예금은 금리를 제공한다.\n\n"
        "채권은 만기와 이자를 가진다.\n\n"
        "주식은 기업의 지분을 나타낸다."
    ).encode()
    document_id: int | None = None

    try:
        with (
            patch(
                "app.application.document_registration.upload_text_object",
                return_value=version_id,
            ),
            patch(
                "app.application.document_registration.download_text_object",
                return_value=stored_content,
            ),
        ):
            document_id, chunk_count = registration_pipeline.register(
                content=stored_content,
                object_key=object_key,
                document_type="textbook",
                category="integration-test",
                title="Hybrid MySQL 통합 테스트",
                original_filename="hybrid_textbook.txt",
                publisher="FirstFolio",
            )

        stored_chunks = chunk_repository.find_all()
        embedding_client = DeterministicFakeEmbedding(size=8)
        hybrid_search = HybridSearch(
            settings=settings,
            bm25_search=BM25Search(
                chunks=stored_chunks,
                tokenizer=KiwiTokenizer(),
            ),
            faiss_search=FaissVectorSearch(
                chunks=stored_chunks,
                embedding_client=embedding_client,
            ),
            chunk_repository=chunk_repository,
        )

        results = hybrid_search.search(unique_search_token)

        assert chunk_count == 3
        assert results
        assert results[0].chunk.document_id == str(document_id)
        assert results[0].chunk.chunk_key == f"{document_id}:0"
        assert unique_search_token in results[0].chunk.content
        assert results[0].score > 0
    finally:
        if document_id is not None:
            _delete_test_document(
                settings,
                document_id,
            )

    if document_id is None:
        raise RuntimeError("Hybrid 통합 테스트 document_id가 생성되지 않았습니다.")

    assert _count_document_rows(
        settings,
        document_id,
    ) == (0, 0)
