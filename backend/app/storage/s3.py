import boto3
from mypy_boto3_s3 import S3Client

from app.settings import settings

s3: S3Client = boto3.client("s3", region_name=settings.AWS_REGION)  # pyright: ignore[reportUnknownMemberType]
