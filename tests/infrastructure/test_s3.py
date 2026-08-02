from unittest.mock import Mock, patch

import pytest

from app.core.config import Settings
from app.infrastructure.s3 import (
    check_s3_connection,
    create_s3_client,
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
