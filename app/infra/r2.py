import io
import logging
import os
import tarfile

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client():
    if not (settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key):
        return None
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


def download_dir(key: str, local_dir: str) -> None:
    """把 R2 上打包的目录拉下来解压到 local_dir，没有对应 key 或未配置 R2 时静默跳过。"""
    client = _client()
    if not client:
        return

    buf = io.BytesIO()
    try:
        client.download_fileobj(settings.r2_bucket, key, buf)
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code not in ("404", "NoSuchKey"):
            logger.warning("R2 download failed for %s: %s", key, e)
        return

    buf.seek(0)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        tar.extractall(local_dir)


def upload_dir(key: str, local_dir: str) -> None:
    """把 local_dir 打包上传到 R2，未配置 R2 或目录不存在时静默跳过。"""
    client = _client()
    if not client or not os.path.isdir(local_dir):
        return

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(local_dir, arcname=".")
    buf.seek(0)

    try:
        client.upload_fileobj(buf, settings.r2_bucket, key)
    except ClientError as e:
        logger.warning("R2 upload failed for %s: %s", key, e)
