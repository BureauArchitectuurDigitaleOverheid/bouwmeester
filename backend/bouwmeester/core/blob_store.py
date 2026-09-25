"""Where bijlagen (attachment files) live: object storage, or a local directory.

In production the files go to the S3-compatible bucket that ZAD's
``minio-storage`` service provides. The backend used to keep them on a
persistent volume under ``/data/bijlagen``, and such a volume can only be
mounted by one pod at a time: every deploy had to stop the old pod before the
new one could start, which measured as 37 seconds of 503s. A bucket has no such
restriction, so with the files there a deploy can start the new pod first.

Keys are the paths the database already stores, relative to the old bijlagen
root: ``<node_id>/<uuid>_<name>`` for a bron, ``leads/<lead_id>/...`` for a
lead and ``chat/<id>/...`` for chat (whose ``pad`` column is relative to
``chat/``, so callers add that prefix). Moving the files therefore needed no
data migration in the database, only a copy of the files themselves.

Without object-store settings (local development, tests) the files stay in a
local directory, behind the same interface.
"""

from __future__ import annotations

import asyncio
import logging
import posixpath
from functools import lru_cache
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class InvalidKeyError(ValueError):
    """A key that is absolute or climbs out of the store with ``..``."""


def normalize_key(key: str) -> str:
    """Return *key* as a clean relative path, or raise ``InvalidKeyError``.

    The keys come from database columns, so they are trusted in origin but
    still checked: a key must never reach outside the store, whether that is a
    directory on disk or a bucket shared with anything else.
    """
    if not key or "\\" in key or "\x00" in key:
        raise InvalidKeyError(key)
    normalized = posixpath.normpath(key)
    if (
        normalized.startswith("/")
        or normalized == "."
        or normalized == ".."
        or normalized.startswith("../")
    ):
        raise InvalidKeyError(key)
    return normalized


class BlobStore(Protocol):
    async def put(
        self, key: str, data: bytes, content_type: str | None = None
    ) -> None: ...

    async def get(self, key: str) -> bytes | None:
        """The object's bytes, or ``None`` when there is no such object."""
        ...

    async def size(self, key: str) -> int | None:
        """The object's size in bytes, or ``None`` when there is no such object."""
        ...

    async def delete(self, key: str) -> None:
        """Remove the object; a missing one is not an error."""
        ...


class LocalBlobStore:
    """Files in a directory, for local development and tests."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, key: str) -> Path:
        path = (self.root / normalize_key(key)).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise InvalidKeyError(key)
        return path

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        await asyncio.to_thread(write)

    async def get(self, key: str) -> bytes | None:
        path = self._path(key)

        def read() -> bytes | None:
            try:
                return path.read_bytes()
            except (FileNotFoundError, IsADirectoryError):
                return None

        return await asyncio.to_thread(read)

    async def size(self, key: str) -> int | None:
        path = self._path(key)

        def stat() -> int | None:
            try:
                return path.stat().st_size if path.is_file() else None
            except OSError:
                return None

        return await asyncio.to_thread(stat)

    async def delete(self, key: str) -> None:
        path = self._path(key)
        await asyncio.to_thread(path.unlink, missing_ok=True)


class S3BlobStore:
    """Objects in an S3-compatible bucket (ZAD's ``minio-storage``).

    boto3 is synchronous, so every call runs in a worker thread. The client is
    thread-safe; the resource objects would not be, which is why this sticks to
    the client API.
    """

    def __init__(self, client, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    @staticmethod
    def _is_missing(exc: Exception) -> bool:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        return code in ("404", "NoSuchKey", "NotFound")

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=normalize_key(key),
            Body=data,
            **extra,
        )

    async def get(self, key: str) -> bytes | None:
        from botocore.exceptions import ClientError

        def read() -> bytes | None:
            try:
                response = self.client.get_object(
                    Bucket=self.bucket, Key=normalize_key(key)
                )
            except ClientError as exc:
                if self._is_missing(exc):
                    return None
                raise
            return response["Body"].read()

        return await asyncio.to_thread(read)

    async def size(self, key: str) -> int | None:
        from botocore.exceptions import ClientError

        def head() -> int | None:
            try:
                response = self.client.head_object(
                    Bucket=self.bucket, Key=normalize_key(key)
                )
            except ClientError as exc:
                if self._is_missing(exc):
                    return None
                raise
            return int(response["ContentLength"])

        return await asyncio.to_thread(head)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(
            self.client.delete_object, Bucket=self.bucket, Key=normalize_key(key)
        )


class FallbackBlobStore:
    """Write to *primary*; read from *primary*, and from *fallback* if it is not there.

    For the move from the volume to the bucket: the copy at startup
    (``scripts/copy_bijlagen_to_object_store.py``) should leave nothing behind,
    but while the volume is still mounted a file it missed stays downloadable
    instead of turning into a 404. Goes away together with the volume.
    """

    def __init__(self, primary: BlobStore, fallback: BlobStore) -> None:
        self.primary = primary
        self.fallback = fallback

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        await self.primary.put(key, data, content_type)

    async def get(self, key: str) -> bytes | None:
        data = await self.primary.get(key)
        if data is None:
            data = await self.fallback.get(key)
            if data is not None:
                logger.warning("Bijlage %s alleen op het volume gevonden", key)
        return data

    async def size(self, key: str) -> int | None:
        found = await self.primary.size(key)
        return found if found is not None else await self.fallback.size(key)

    async def delete(self, key: str) -> None:
        await self.primary.delete(key)
        await self.fallback.delete(key)


def s3_client_from_settings():
    """A boto3 S3 client for the configured object store, or ``None``."""
    from bouwmeester.core.config import get_settings

    settings = get_settings()
    if not settings.object_store_configured:
        return None

    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.OBJECT_STORE_ENDPOINT_URL,
        aws_access_key_id=settings.OBJECT_STORE_USER,
        aws_secret_access_key=settings.OBJECT_STORE_PASSWORD,
        region_name=settings.OBJECT_STORE_REGION or "us-east-1",
        # MinIO serves buckets under the path, not as a subdomain.
        config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
    )


_override: BlobStore | None = None


@lru_cache
def _configured_store() -> BlobStore:
    from bouwmeester.core.config import get_settings
    from bouwmeester.core.storage import bijlagen_root

    client = s3_client_from_settings()
    if client is None:
        logger.info("Bijlagen: lokale opslag in %s", bijlagen_root())
        return LocalBlobStore(bijlagen_root())
    bucket = get_settings().OBJECT_STORE_BUCKET_NAME
    s3 = S3BlobStore(client, bucket)
    local_root = bijlagen_root()
    if local_root.is_dir():
        logger.info(
            "Bijlagen: objectopslag, bucket %s, met %s als terugval", bucket, local_root
        )
        return FallbackBlobStore(s3, LocalBlobStore(local_root))
    logger.info("Bijlagen: objectopslag, bucket %s", bucket)
    return s3


def get_blob_store() -> BlobStore:
    """The store the app writes bijlagen to and reads them from."""
    return _override if _override is not None else _configured_store()


def set_blob_store(store: BlobStore | None) -> None:
    """Point the app at *store*; ``None`` restores the configured one. For tests."""
    global _override
    _override = store
