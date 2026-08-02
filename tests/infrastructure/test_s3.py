from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.s3 import (
    check_s3_connection,
    create_s3_client,
    download_binary_object,
    download_text_object,
    upload_binary_object,
    upload_text_object,
)


@patch("app.infrastructure.s3.boto3.client")
def test_create_s3_client_with_settings(
    boto3_client_mock: Mock,
) -> None:
    client = Mock()
    boto3_client_mock.return_value = client

    settings = Settings(
        aws_region="ap-northeast-2",
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    result = create_s3_client(settings)

    assert result is client
    boto3_client_mock.assert_called_once_with(
        "s3",
        region_name="ap-northeast-2",
    )


@patch("app.infrastructure.s3.boto3.client")
def test_reject_empty_s3_bucket_name(
    boto3_client_mock: Mock,
) -> None:
    settings = Settings(
        s3_bucket_name="   ",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="S3_BUCKET_NAME",
    ):
        create_s3_client(settings)

    boto3_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_return_true_when_bucket_versioning_is_enabled(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_bucket_versioning.return_value = {
        "Status": "Enabled",
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    connected = check_s3_connection(settings)

    assert connected is True
    client.get_bucket_versioning.assert_called_once_with(
        Bucket="test-rag-bucket",
    )
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_return_false_when_bucket_versioning_is_suspended(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_bucket_versioning.return_value = {
        "Status": "Suspended",
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    connected = check_s3_connection(settings)

    assert connected is False
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_return_false_when_bucket_versioning_status_is_missing(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_bucket_versioning.return_value = {}
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    connected = check_s3_connection(settings)

    assert connected is False
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_client_when_connection_check_fails(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_bucket_versioning.side_effect = RuntimeError(
        "S3 unavailable",
    )
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 unavailable",
    ):
        check_s3_connection(settings)

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_upload_text_object_returns_version_id(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.return_value = {
        "VersionId": "version-001",
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )
    content = "금융 교과서 테스트".encode()

    version_id = upload_text_object(
        settings,
        "documents/financial_textbook.txt",
        content,
    )

    assert version_id == "version-001"
    client.put_object.assert_called_once_with(
        Bucket="test-rag-bucket",
        Key="documents/financial_textbook.txt",
        Body=content,
        ContentType="text/plain; charset=utf-8",
    )
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_empty_s3_object_key(
    create_client_mock: Mock,
) -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="object_key",
    ):
        upload_text_object(
            settings,
            "   ",
            b"test content",
        )

    create_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_upload_response_without_version_id(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.return_value = {}
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="VersionId",
    ):
        upload_text_object(
            settings,
            "documents/test.txt",
            b"test content",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_client_when_upload_fails(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.side_effect = RuntimeError(
        "S3 upload failed",
    )
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 upload failed",
    ):
        upload_text_object(
            settings,
            "documents/test.txt",
            b"test content",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_download_text_object_by_version_id(
    create_client_mock: Mock,
) -> None:
    response_body = Mock()
    response_body.read.return_value = b"financial textbook"

    client = Mock()
    client.get_object.return_value = {
        "Body": response_body,
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    content = download_text_object(
        settings,
        "documents/financial_textbook.txt",
        "version-001",
    )

    assert content == b"financial textbook"
    client.get_object.assert_called_once_with(
        Bucket="test-rag-bucket",
        Key="documents/financial_textbook.txt",
        VersionId="version-001",
    )
    response_body.read.assert_called_once_with()
    response_body.close.assert_called_once_with()
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_empty_download_object_key(
    create_client_mock: Mock,
) -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="object_key",
    ):
        download_text_object(
            settings,
            "   ",
            "version-001",
        )

    create_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_empty_download_version_id(
    create_client_mock: Mock,
) -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="version_id",
    ):
        download_text_object(
            settings,
            "documents/test.txt",
            "   ",
        )

    create_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_client_when_download_fails(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_object.side_effect = RuntimeError(
        "S3 download failed",
    )
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 download failed",
    ):
        download_text_object(
            settings,
            "documents/test.txt",
            "version-001",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_resources_when_body_read_fails(
    create_client_mock: Mock,
) -> None:
    response_body = Mock()
    response_body.read.side_effect = RuntimeError(
        "S3 body read failed",
    )

    client = Mock()
    client.get_object.return_value = {
        "Body": response_body,
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 body read failed",
    ):
        download_text_object(
            settings,
            "documents/test.txt",
            "version-001",
        )

    response_body.close.assert_called_once_with()
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_upload_binary_object_returns_version_id(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.return_value = {
        "VersionId": "faiss-version-001",
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )
    content = b"faiss-index-bytes"

    version_id = upload_binary_object(
        settings,
        "indexes/financial.faiss",
        content,
    )

    assert version_id == "faiss-version-001"
    client.put_object.assert_called_once_with(
        Bucket="test-rag-bucket",
        Key="indexes/financial.faiss",
        Body=content,
        ContentType="application/octet-stream",
    )
    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_empty_binary_upload_object_key(
    create_client_mock: Mock,
) -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match="object_key",
    ):
        upload_binary_object(
            settings,
            "   ",
            b"faiss-index-bytes",
        )

    create_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_reject_binary_upload_response_without_version_id(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.return_value = {}
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="VersionId",
    ):
        upload_binary_object(
            settings,
            "indexes/financial.faiss",
            b"faiss-index-bytes",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_client_when_binary_upload_fails(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.put_object.side_effect = RuntimeError("S3 binary upload failed")
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 binary upload failed",
    ):
        upload_binary_object(
            settings,
            "indexes/financial.faiss",
            b"faiss-index-bytes",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_download_binary_object_by_version_id(
    create_client_mock: Mock,
) -> None:
    response_body = Mock()
    response_body.read.return_value = b"faiss-index-bytes"

    client = Mock()
    client.get_object.return_value = {
        "Body": response_body,
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    content = download_binary_object(
        settings,
        "indexes/financial.faiss",
        "faiss-version-001",
    )

    assert content == b"faiss-index-bytes"
    client.get_object.assert_called_once_with(
        Bucket="test-rag-bucket",
        Key="indexes/financial.faiss",
        VersionId="faiss-version-001",
    )
    response_body.read.assert_called_once_with()
    response_body.close.assert_called_once_with()
    client.close.assert_called_once_with()


@pytest.mark.parametrize(
    ("object_key", "version_id", "error_message"),
    [
        ("   ", "faiss-version-001", "object_key"),
        ("indexes/financial.faiss", "   ", "version_id"),
    ],
)
@patch("app.infrastructure.s3.create_s3_client")
def test_reject_empty_binary_download_identifier(
    create_client_mock: Mock,
    object_key: str,
    version_id: str,
    error_message: str,
) -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        ValueError,
        match=error_message,
    ):
        download_binary_object(
            settings,
            object_key,
            version_id,
        )

    create_client_mock.assert_not_called()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_client_when_binary_download_fails(
    create_client_mock: Mock,
) -> None:
    client = Mock()
    client.get_object.side_effect = RuntimeError("S3 binary download failed")
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 binary download failed",
    ):
        download_binary_object(
            settings,
            "indexes/financial.faiss",
            "faiss-version-001",
        )

    client.close.assert_called_once_with()


@patch("app.infrastructure.s3.create_s3_client")
def test_close_s3_resources_when_binary_body_read_fails(
    create_client_mock: Mock,
) -> None:
    response_body = Mock()
    response_body.read.side_effect = RuntimeError("S3 binary body read failed")

    client = Mock()
    client.get_object.return_value = {
        "Body": response_body,
    }
    create_client_mock.return_value = client

    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 binary body read failed",
    ):
        download_binary_object(
            settings,
            "indexes/financial.faiss",
            "faiss-version-001",
        )

    response_body.close.assert_called_once_with()
    client.close.assert_called_once_with()
