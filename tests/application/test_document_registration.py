from unittest.mock import Mock, patch

import pytest

from app.application.document_registration import TextDocumentRegistrationPipeline
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.document import DocumentMetadata
from app.infrastructure.document_loaders.text import EmptyDocumentError


def _settings() -> Settings:
    return Settings(
        mysql_password="test-password",
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_register_text_document(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-001"
    download_mock.return_value = (
        "1) 예금의 의미\n예금에 대한 설명.\n\n채권에 대한 설명."
    ).encode()

    connection = Mock()
    create_connection_mock.return_value = connection

    document_repository = Mock()
    document_repository.create_in_transaction.return_value = 12
    chunk_repository = Mock()
    index_invalidator = Mock()
    settings = _settings()

    pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        index_invalidator=index_invalidator,
    )

    document_id, chunk_count = pipeline.register(
        content=b"uploaded content",
        object_key="documents/financial_textbook.txt",
        document_type="textbook",
        category="financial-education",
        title="금융 교과서",
        original_filename="financial_textbook.txt",
        publisher="FirstFolio",
    )

    assert document_id == 12
    assert chunk_count == 2

    upload_mock.assert_called_once_with(
        settings=settings,
        object_key="documents/financial_textbook.txt",
        content=b"uploaded content",
    )
    download_mock.assert_called_once_with(
        settings=settings,
        object_key="documents/financial_textbook.txt",
        version_id="version-001",
    )
    document_repository.create_in_transaction.assert_called_once_with(
        connection=connection,
        document=DocumentMetadata(
            document_type="textbook",
            category="financial-education",
            title="금융 교과서",
            original_filename="financial_textbook.txt",
            content_type="text/plain",
            s3_object_key="documents/financial_textbook.txt",
            s3_version_id="version-001",
            source_url=None,
            publisher="FirstFolio",
            published_at=None,
            status="pending",
        ),
    )

    replacement_call = chunk_repository.replace_document_chunks_in_transaction.call_args
    chunks = replacement_call.kwargs["chunks"]

    assert replacement_call.kwargs["connection"] is connection
    assert replacement_call.kwargs["document_id"] == "12"
    assert [chunk.chunk_key for chunk in chunks] == [
        "12:0",
        "12:1",
    ]
    assert [chunk.content for chunk in chunks] == [
        "1) 예금의 의미\n예금에 대한 설명.",
        "채권에 대한 설명.",
    ]
    assert [chunk.heading for chunk in chunks] == [
        "예금의 의미",
        "예금의 의미",
    ]
    assert all(
        chunk.metadata == {"subsection_heading": chunk.heading} for chunk in chunks
    )
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()
    index_invalidator.assert_called_once_with()


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_register_non_textbook_without_heading_metadata(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-001"
    download_mock.return_value = b"1) numbered report heading\nreport content"
    connection = Mock()
    create_connection_mock.return_value = connection
    document_repository = Mock()
    document_repository.create_in_transaction.return_value = 12
    chunk_repository = Mock()
    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
    )

    pipeline.register(
        content=b"uploaded content",
        object_key="documents/report.txt",
        document_type="report",
        title="금융 보고서",
        original_filename="report.txt",
    )

    replacement_call = chunk_repository.replace_document_chunks_in_transaction.call_args
    chunks = replacement_call.kwargs["chunks"]

    assert len(chunks) == 1
    assert chunks[0].heading is None


@patch("app.application.document_registration.upload_text_object")
def test_reject_empty_document_before_s3_upload(
    upload_mock: Mock,
) -> None:
    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=Mock(),
        chunk_repository=Mock(),
    )

    with pytest.raises(
        EmptyDocumentError,
        match="문서에 내용이 없습니다",
    ):
        pipeline.register(
            content=b"  \n\t",
            object_key="documents/empty.txt",
            document_type="textbook",
            title="빈 문서",
            original_filename="empty.txt",
        )

    upload_mock.assert_not_called()


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_do_not_start_mysql_when_s3_download_fails(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-001"
    download_mock.side_effect = RuntimeError("S3 download failed")
    document_repository = Mock()
    chunk_repository = Mock()

    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 download failed",
    ):
        pipeline.register(
            content=b"financial textbook",
            object_key="documents/financial_textbook.txt",
            document_type="textbook",
            title="금융 교과서",
            original_filename="financial_textbook.txt",
        )

    create_connection_mock.assert_not_called()
    document_repository.create_in_transaction.assert_not_called()
    chunk_repository.replace_document_chunks_in_transaction.assert_not_called()


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_roll_back_document_when_chunk_storage_fails(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-001"
    download_mock.return_value = b"financial textbook"

    connection = Mock()
    create_connection_mock.return_value = connection

    document_repository = Mock()
    document_repository.create_in_transaction.return_value = 12

    chunk_repository = Mock()
    chunk_repository.replace_document_chunks_in_transaction.side_effect = RuntimeError(
        "chunk storage failed"
    )
    index_invalidator = Mock()

    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        index_invalidator=index_invalidator,
    )

    with pytest.raises(
        RuntimeError,
        match="chunk storage failed",
    ):
        pipeline.register(
            content=b"financial textbook",
            object_key="documents/financial_textbook.txt",
            document_type="textbook",
            title="금융 교과서",
            original_filename="financial_textbook.txt",
        )

    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()
    index_invalidator.assert_not_called()


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_register_selects_chunker_by_document_type(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-001"
    download_mock.return_value = b"news content"
    connection = Mock()
    create_connection_mock.return_value = connection
    document_repository = Mock()
    document_repository.create_in_transaction.return_value = 12
    chunk_repository = Mock()
    selected_chunk = DocumentChunk(
        document_id="12",
        chunk_key="12:0",
        sequence=0,
        content="selected news chunk",
        title="News",
        source="news.txt",
    )
    document_chunker = Mock()
    document_chunker.chunk.return_value = [selected_chunk]
    chunker_registry = Mock()
    chunker_registry.get.return_value = document_chunker
    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        chunker_registry=chunker_registry,
    )

    document_id, chunk_count = pipeline.register(
        content=b"news content",
        object_key="documents/news.txt",
        document_type="news",
        title="News",
        original_filename="news.txt",
    )

    assert document_id == 12
    assert chunk_count == 1
    chunker_registry.get.assert_called_once_with("news")
    document_chunker.chunk.assert_called_once()
    replacement_call = chunk_repository.replace_document_chunks_in_transaction.call_args
    assert replacement_call.kwargs["chunks"] == [selected_chunk]


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_replace_selects_chunker_from_stored_document_type(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-002"
    download_mock.return_value = b"updated news content"
    connection = Mock()
    create_connection_mock.return_value = connection
    document_repository = Mock()
    document_repository.find_by_id.return_value = DocumentMetadata(
        document_id=12,
        document_type="news",
        category="finance",
        title="News",
        original_filename="news.txt",
        content_type="text/plain",
        s3_object_key="documents/news.txt",
        s3_version_id="version-001",
        status="ready",
    )
    chunk_repository = Mock()
    selected_chunk = DocumentChunk(
        document_id="12",
        chunk_key="12:0",
        sequence=0,
        content="selected updated news chunk",
        title="News",
        source="news.txt",
    )
    document_chunker = Mock()
    document_chunker.chunk.return_value = [selected_chunk]
    chunker_registry = Mock()
    chunker_registry.get.return_value = document_chunker
    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        chunker_registry=chunker_registry,
    )

    chunk_count = pipeline.replace(document_id=12, content=b"updated news content")

    assert chunk_count == 1
    chunker_registry.get.assert_called_once_with("news")
    document_chunker.chunk.assert_called_once()
    replacement_call = chunk_repository.replace_document_chunks_in_transaction.call_args
    assert replacement_call.kwargs["chunks"] == [selected_chunk]


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_replace_text_document(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-002"
    download_mock.return_value = (
        "2) 새 예금 단원\n새 예금 설명.\n\n새 채권 설명."
    ).encode()
    connection = Mock()
    create_connection_mock.return_value = connection
    document_repository = Mock()
    document_repository.find_by_id.return_value = DocumentMetadata(
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
        published_at=None,
        status="ready",
    )
    chunk_repository = Mock()
    index_invalidator = Mock()
    settings = _settings()
    pipeline = TextDocumentRegistrationPipeline(
        settings=settings,
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        index_invalidator=index_invalidator,
    )

    chunk_count = pipeline.replace(
        document_id=12,
        content=b"updated content",
    )

    assert chunk_count == 2
    upload_mock.assert_called_once_with(
        settings=settings,
        object_key="documents/financial_textbook.txt",
        content=b"updated content",
    )
    download_mock.assert_called_once_with(
        settings=settings,
        object_key="documents/financial_textbook.txt",
        version_id="version-002",
    )
    replacement_call = chunk_repository.replace_document_chunks_in_transaction.call_args
    assert replacement_call.kwargs["connection"] is connection
    assert replacement_call.kwargs["document_id"] == "12"
    assert [chunk.chunk_key for chunk in replacement_call.kwargs["chunks"]] == [
        "12:0",
        "12:1",
    ]
    assert [chunk.heading for chunk in replacement_call.kwargs["chunks"]] == [
        "새 예금 단원",
        "새 예금 단원",
    ]
    replacement_chunks = replacement_call.kwargs["chunks"]
    assert all(
        chunk.metadata == {"subsection_heading": chunk.heading}
        for chunk in replacement_chunks
    )
    document_repository.update_storage_in_transaction.assert_called_once_with(
        connection=connection,
        document_id=12,
        s3_object_key="documents/financial_textbook.txt",
        s3_version_id="version-002",
        status="pending",
    )
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()
    index_invalidator.assert_called_once_with()


@patch("app.application.document_registration.create_mysql_connection")
@patch("app.application.document_registration.download_text_object")
@patch("app.application.document_registration.upload_text_object")
def test_roll_back_replacement_when_document_update_fails(
    upload_mock: Mock,
    download_mock: Mock,
    create_connection_mock: Mock,
) -> None:
    upload_mock.return_value = "version-002"
    download_mock.return_value = b"updated content"
    connection = Mock()
    create_connection_mock.return_value = connection
    document_repository = Mock()
    document_repository.find_by_id.return_value = DocumentMetadata(
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
        published_at=None,
        status="ready",
    )
    document_repository.update_storage_in_transaction.side_effect = RuntimeError(
        "document update failed"
    )
    chunk_repository = Mock()
    index_invalidator = Mock()
    pipeline = TextDocumentRegistrationPipeline(
        settings=_settings(),
        document_repository=document_repository,
        chunk_repository=chunk_repository,
        index_invalidator=index_invalidator,
    )

    with pytest.raises(
        RuntimeError,
        match="document update failed",
    ):
        pipeline.replace(
            document_id=12,
            content=b"updated content",
        )

    chunk_repository.replace_document_chunks_in_transaction.assert_called_once()
    connection.commit.assert_not_called()
    connection.rollback.assert_called_once_with()
    connection.close.assert_called_once_with()
    index_invalidator.assert_not_called()
