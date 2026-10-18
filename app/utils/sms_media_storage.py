"""Publish SMS media assets to S3-compatible storage with SigV4."""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os
import posixpath
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

SERVICE = "s3"
DEFAULT_PREFIX = "twilio-snapshots"


class SmsMediaStorageConfigError(RuntimeError):
    """Raised when storage publishing is not configured."""


class SmsMediaStoragePublishError(RuntimeError):
    """Raised when storage upload or signing fails."""


@dataclass(frozen=True)
class PublishedSmsMedia:
    """S3 object metadata and a short-lived public GET URL."""

    key: str
    media_url: str
    expires_at: int
    expires_seconds: int


def missing_storage_config() -> list[str]:
    """Return required storage setting names that are currently unset."""

    return [name for name in _required_names() if not _env(name)]


def publish_sms_media(
    *,
    camera: str,
    body: bytes,
    content_type: str,
    extension: str = "gif",
) -> PublishedSmsMedia:
    """Upload media bytes and return a short-lived signed GET URL."""

    missing = missing_storage_config()
    if missing:
        raise SmsMediaStorageConfigError(
            "missing required SMS media storage env: " + ", ".join(missing)
        )
    key = _object_key(camera, extension)
    _sigv4_put_object(key, body, content_type)
    expires = _presign_expires_seconds()
    return PublishedSmsMedia(
        key=key,
        media_url=_presigned_get_url(key, expires),
        expires_at=int(time.time()) + expires,
        expires_seconds=expires,
    )


def _required_names() -> list[str]:
    return [
        "BUCKET",
        "REGION",
        "ENDPOINT_URL",
        "ACCESS_KEY_ID",
        "SECRET_ACCESS_KEY",
    ]


def _env(name: str, default: str = "") -> str:
    primary = os.environ.get(f"GLIMPSER_SMS_MEDIA_{name}", "").strip()
    if primary:
        return primary
    legacy = os.environ.get(f"TWILIO_SNAPSHOT_{name}", "").strip()
    if legacy:
        return legacy
    return default


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _aws_quote(value: str, safe: str = "-_.~") -> str:
    return urllib.parse.quote(str(value), safe=safe)


def _quote_key_path(key: str) -> str:
    return "/".join(_aws_quote(part) for part in key.split("/"))


def _object_path(bucket: str, key: str) -> str:
    return "/" + _aws_quote(bucket) + "/" + _quote_key_path(key)


def _signing_key(secret_key: str, datestamp: str, region: str) -> bytes:
    key = ("AWS4" + secret_key).encode("utf-8")
    for msg in [datestamp, region, SERVICE, "aws4_request"]:
        key = hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()
    return key


def _canonical_query(params: dict[str, str]) -> str:
    return "&".join(
        f"{_aws_quote(key)}={_aws_quote(value)}"
        for key, value in sorted(params.items())
    )


def _endpoint_base() -> str:
    return _env("ENDPOINT_URL").rstrip("/")


def _endpoint_host() -> str:
    parsed = urllib.parse.urlsplit(_endpoint_base())
    if not parsed.scheme or not parsed.netloc:
        raise SmsMediaStorageConfigError(
            "GLIMPSER_SMS_MEDIA_ENDPOINT_URL must be an absolute URL"
        )
    return parsed.netloc


def _object_url(bucket: str, key: str) -> str:
    return _endpoint_base() + _object_path(bucket, key)


def _sigv4_put_object(key: str, body: bytes, content_type: str) -> None:
    access_key = _env("ACCESS_KEY_ID")
    secret_key = _env("SECRET_ACCESS_KEY")
    bucket = _env("BUCKET")
    region = _env("REGION")
    now = dt.datetime.utcnow()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    scope = f"{datestamp}/{region}/{SERVICE}/aws4_request"
    host = _endpoint_host()
    uri = _object_path(bucket, key)
    payload_hash = hashlib.sha256(body).hexdigest()

    headers_to_sign = {
        "cache-control": f"private, max-age={_presign_expires_seconds()}",
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amzdate,
    }
    signed_headers = ";".join(sorted(headers_to_sign))
    canonical_headers = "".join(
        f"{name}:{' '.join(value.split())}\n"
        for name, value in sorted(headers_to_sign.items())
    )
    canonical_request = "\n".join(
        ["PUT", uri, "", canonical_headers, signed_headers, payload_hash]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amzdate,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(secret_key, datestamp, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    authorization = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    headers = {
        "Authorization": authorization,
        "Cache-Control": headers_to_sign["cache-control"],
        "Content-Type": content_type,
        "Host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amzdate,
    }
    req = urllib.request.Request(
        _object_url(bucket, key),
        data=body,
        headers=headers,
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=_upload_timeout_seconds()) as resp:
            if resp.status < 200 or resp.status >= 300:
                raise SmsMediaStoragePublishError(
                    f"object upload failed status={resp.status}"
                )
    except urllib.error.HTTPError as exc:
        detail = exc.read(512).decode("utf-8", "replace")
        raise SmsMediaStoragePublishError(
            f"object upload failed status={exc.code}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SmsMediaStoragePublishError(
            f"object upload failed: {exc.reason}"
        ) from exc


def _presigned_get_url(key: str, expires: int) -> str:
    access_key = _env("ACCESS_KEY_ID")
    secret_key = _env("SECRET_ACCESS_KEY")
    bucket = _env("BUCKET")
    region = _env("REGION")
    now = dt.datetime.utcnow()
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    scope = f"{datestamp}/{region}/{SERVICE}/aws4_request"
    host = _endpoint_host()
    uri = _object_path(bucket, key)
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{scope}",
        "X-Amz-Date": amzdate,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_request = "\n".join(
        [
            "GET",
            uri,
            _canonical_query(params),
            f"host:{host}\n",
            "host",
            "UNSIGNED-PAYLOAD",
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amzdate,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(secret_key, datestamp, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params["X-Amz-Signature"] = signature
    return _endpoint_base() + uri + "?" + _canonical_query(params)


def _presign_expires_seconds() -> int:
    return _env_int("EXPIRES_SECONDS", 300, 30, 3600)


def _upload_timeout_seconds() -> int:
    return _env_int("UPLOAD_TIMEOUT_SECONDS", 20, 3, 120)


def _object_key(camera: str, extension: str) -> str:
    prefix = _env("KEY_PREFIX", DEFAULT_PREFIX).strip("/")
    stamp = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    token = secrets.token_urlsafe(9).replace("-", "").replace("_", "")
    safe_camera = re.sub(r"[^A-Za-z0-9_.-]+", "_", camera).strip("._-") or "camera"
    safe_ext = re.sub(r"[^A-Za-z0-9]+", "", extension).lower() or "bin"
    return posixpath.join(prefix, safe_camera, f"{stamp}-{token}.{safe_ext}")
