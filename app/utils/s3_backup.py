import os
import tarfile
import tempfile
import logging

try:
    import boto3
except Exception:  # boto3 might not be installed
    boto3 = None


def _env(var, default=None):
    return os.getenv(var, default)


def _get_s3_client():
    bucket = _env("GLIMPSER_S3_BUCKET")
    access_key = _env("AWS_ACCESS_KEY_ID")
    secret_key = _env("AWS_SECRET_ACCESS_KEY")
    region = _env("AWS_DEFAULT_REGION", "us-east-1")
    if not (boto3 and bucket and access_key and secret_key):
        return None, None
    try:
        client = boto3.client(
            "s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        return client, bucket
    except Exception as exc:
        logging.error("Failed to create S3 client: %s", exc)
        return None, None


def upload_file(path: str, key: str) -> bool:
    client, bucket = _get_s3_client()
    if client is None:
        return False
    try:
        client.upload_file(path, bucket, key)
        return True
    except Exception as exc:
        logging.error("Failed to upload %s to S3: %s", path, exc)
        return False


def download_file(key: str, path: str) -> bool:
    client, bucket = _get_s3_client()
    if client is None:
        return False
    try:
        client.download_file(bucket, key, path)
        return True
    except Exception as exc:
        logging.error("Failed to download %s from S3: %s", key, exc)
        return False


def upload_media_archive() -> bool:
    client, bucket = _get_s3_client()
    if client is None:
        return False
    screenshot_dir = _env("SCREENSHOT_DIRECTORY", "data/screenshots/")
    video_dir = _env("VIDEO_DIRECTORY", "data/video/")
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    archive_path = temp_file.name
    temp_file.close()
    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            if os.path.isdir(screenshot_dir):
                tar.add(screenshot_dir, arcname=os.path.basename(screenshot_dir))
            if os.path.isdir(video_dir):
                tar.add(video_dir, arcname=os.path.basename(video_dir))
        client.upload_file(archive_path, bucket, "media_backup.tar.gz")
        return True
    except Exception as exc:
        logging.error("Failed to create/upload media archive: %s", exc)
        return False
    finally:
        if os.path.exists(archive_path):
            os.remove(archive_path)
