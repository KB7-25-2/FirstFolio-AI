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
