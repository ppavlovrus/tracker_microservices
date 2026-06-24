"""S3-compatible object storage (MinIO) access for the attachments service.

Uploads/downloads never flow through this service or the message bus: the
client talks to the object store directly via presigned URLs. This module only
generates those URLs (a local signing operation, no network call) and performs
the few server-side operations the service still owns: ensuring the bucket
exists and deleting objects.
"""

import asyncio
import logging
import os
import uuid

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


def build_object_key(task_id: int, filename: str) -> str:
    """Build a collision-free object key, namespaced per task."""
    safe_name = os.path.basename(str(filename)).replace("/", "_") or "file"
    return f"task_{task_id}/{uuid.uuid4().hex}_{safe_name}"


class S3Storage:
    """Thin wrapper over two boto3 S3 clients (internal ops + public presign)."""

    def __init__(
        self,
        *,
        internal_endpoint: str,
        public_endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str,
        presign_expire: int,
    ):
        self.bucket = bucket
        self.presign_expire = presign_expire

        # MinIO needs path-style addressing and SigV4.
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        common = dict(
            service_name="s3",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=cfg,
        )
        # Server-side operations go over the in-network endpoint.
        self._internal = boto3.client(endpoint_url=internal_endpoint, **common)
        # Presigned URLs must point at an endpoint the client can reach; the
        # signature is bound to that host, so a separate client is required.
        self._public = boto3.client(endpoint_url=public_endpoint, **common)

    def presigned_put_url(self, key: str) -> str:
        """Presigned URL the client uses to PUT the file bytes directly."""
        return self._public.generate_presigned_url(
            "put_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presign_expire,
        )

    def presigned_get_url(self, key: str) -> str:
        """Presigned URL the client uses to GET (download) the file bytes."""
        return self._public.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.presign_expire,
        )

    def _ensure_bucket_sync(self) -> None:
        try:
            self._internal.head_bucket(Bucket=self.bucket)
        except ClientError:
            self._internal.create_bucket(Bucket=self.bucket)

    async def ensure_bucket(self, *, retries: int = 15, delay: float = 2.0) -> None:
        """Create the bucket if missing, retrying while MinIO is still starting."""
        for attempt in range(1, retries + 1):
            try:
                await asyncio.to_thread(self._ensure_bucket_sync)
                logger.info(f"S3 bucket ready: {self.bucket}")
                return
            except Exception as e:
                logger.warning(
                    f"S3 not ready (attempt {attempt}/{retries}): {e}"
                )
                await asyncio.sleep(delay)
        raise RuntimeError(f"S3 bucket '{self.bucket}' could not be ensured")

    def _delete_sync(self, key: str) -> None:
        self._internal.delete_object(Bucket=self.bucket, Key=key)

    async def delete(self, key: str) -> None:
        """Delete an object from the bucket."""
        await asyncio.to_thread(self._delete_sync, key)
