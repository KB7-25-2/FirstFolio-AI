import boto3
from botocore.client import BaseClient

from app.core.config import Settings


def create_s3_client(
    settings: Settings,
) -> BaseClient:
    if not settings.s3_bucket_name.strip():
        raise ValueError("S3_BUCKET_NAME 환경변수가 비어 있습니다.")

    return boto3.client(
        "s3",
        region_name=settings.aws_region,
    )


def check_s3_connection(
    settings: Settings,
) -> bool:
    client = create_s3_client(settings)

    try:
        response = client.get_bucket_versioning(
            Bucket=settings.s3_bucket_name,
        )

        return response.get("Status") == "Enabled"
    finally:
        client.close()


def upload_text_object(
    settings: Settings,
    object_key: str,
    content: bytes,
) -> str:
    if not object_key.strip():
        raise ValueError("S3 object_key는 비어 있을 수 없습니다.")

    client = create_s3_client(settings)

    try:
        response = client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            Body=content,
            ContentType="text/plain; charset=utf-8",
        )

        version_id = response.get("VersionId")

        if not isinstance(version_id, str) or not version_id.strip():
            raise RuntimeError("S3 업로드 응답에 VersionId가 없습니다.")

        return version_id
    finally:
        client.close()


def upload_binary_object(
    settings: Settings,
    object_key: str,
    content: bytes,
) -> str:
    if not object_key.strip():
        raise ValueError("S3 object_key는 비어 있을 수 없습니다.")

    client = create_s3_client(settings)

    try:
        response = client.put_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            Body=content,
            ContentType="application/octet-stream",
        )

        version_id = response.get("VersionId")

        if not isinstance(version_id, str) or not version_id.strip():
            raise RuntimeError("S3 업로드 응답에 VersionId가 없습니다.")

        return version_id
    finally:
        client.close()


def download_text_object(
    settings: Settings,
    object_key: str,
    version_id: str,
) -> bytes:
    if not object_key.strip():
        raise ValueError("S3 object_key는 비어 있을 수 없습니다.")

    if not version_id.strip():
        raise ValueError("S3 version_id는 비어 있을 수 없습니다.")

    client = create_s3_client(settings)
    response_body = None

    try:
        response = client.get_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            VersionId=version_id,
        )
        response_body = response["Body"]

        content = response_body.read()

        if not isinstance(content, bytes):
            raise RuntimeError("S3 원문 응답이 bytes 형식이 아닙니다.")

        return content
    finally:
        try:
            if response_body is not None:
                response_body.close()
        finally:
            client.close()


def download_binary_object(
    settings: Settings,
    object_key: str,
    version_id: str,
) -> bytes:
    if not object_key.strip():
        raise ValueError("S3 object_key는 비어 있을 수 없습니다.")

    if not version_id.strip():
        raise ValueError("S3 version_id는 비어 있을 수 없습니다.")

    client = create_s3_client(settings)
    response_body = None

    try:
        response = client.get_object(
            Bucket=settings.s3_bucket_name,
            Key=object_key,
            VersionId=version_id,
        )
        response_body = response["Body"]

        content = response_body.read()

        if not isinstance(content, bytes):
            raise RuntimeError("S3 바이너리 응답이 bytes 형식이 아닙니다.")

        return content
    finally:
        try:
            if response_body is not None:
                response_body.close()
        finally:
            client.close()
