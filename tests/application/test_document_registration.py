from unittest.mock import Mock, patch

import pytest

from app.application.document_registration import TextDocumentRegistrationPipeline
from app.core.config import Settings
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
    download_mock.return_value = ("예금에 대한 설명.\n\n채권에 대한 설명.").encode()

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
        "예금에 대한 설명.",
        "채권에 대한 설명.",
    ]
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once_with()
    index_invalidator.assert_called_once_with()


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
