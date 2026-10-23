"""Encrypted document storage (M2).

Files are encrypted with Fernet (AES-128-CBC + HMAC) before they reach the backing
store, so neither the local disk nor the S3 bucket ever holds plaintext.
"""

import hashlib
import secrets
from pathlib import Path
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import Settings


class StorageError(RuntimeError):
    pass


class BlobStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalBlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise StorageError(f"Invalid storage key: {key}")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise StorageError(f"Not found: {key}")
        return path.read_bytes()


class S3BlobStore:
    def __init__(self, settings: Settings):
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name="us-east-1",
        )

    def ensure_bucket(self) -> None:
        existing = {b["Name"] for b in self.client.list_buckets().get("Buckets", [])}
        if self.bucket not in existing:
            self.client.create_bucket(Bucket=self.bucket)

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def get(self, key: str) -> bytes:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except self.client.exceptions.NoSuchKey as exc:
            raise StorageError(f"Not found: {key}") from exc


class DocumentStore:
    """Encrypts on write, decrypts on read, and names objects with random keys."""

    def __init__(self, backend: BlobStore, encryption_key: str):
        if not encryption_key:
            raise StorageError(
                "DT_STORAGE_ENCRYPTION_KEY is not set. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        self.backend = backend
        self.fernet = Fernet(encryption_key.encode())

    def save(self, data: bytes) -> tuple[str, str]:
        """Store bytes; return (storage_key, sha256 of the plaintext)."""
        digest = hashlib.sha256(data).hexdigest()
        key = f"documents/{secrets.token_hex(2)}/{secrets.token_hex(16)}"
        self.backend.put(key, self.fernet.encrypt(data))
        return key, digest

    def load(self, key: str) -> bytes:
        try:
            return self.fernet.decrypt(self.backend.get(key))
        except InvalidToken as exc:
            raise StorageError("Stored document failed integrity check") from exc


def build_store(settings: Settings) -> DocumentStore:
    if settings.storage_backend == "local":
        backend: BlobStore = LocalBlobStore(settings.storage_local_dir)
    else:
        s3 = S3BlobStore(settings)
        s3.ensure_bucket()
        backend = s3
    return DocumentStore(backend, settings.storage_encryption_key)
