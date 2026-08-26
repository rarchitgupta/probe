from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config


@dataclass(frozen=True)
class StoredArtifact:
    storage: str
    key: str
    size_bytes: int


class ArtifactStorage(Protocol):
    name: str

    async def store(
        self, path: Path, key: str, content_type: str
    ) -> StoredArtifact: ...

    def signed_url(self, key: str) -> str | None: ...


class LocalArtifactStorage:
    name = "local"

    async def store(self, path: Path, key: str, content_type: str) -> StoredArtifact:
        return StoredArtifact(self.name, str(path), path.stat().st_size)

    def signed_url(self, key: str) -> None:
        return None


class S3ArtifactStorage:
    name = "s3"

    def __init__(
        self,
        *,
        endpoint_url: str,
        public_endpoint_url: str,
        region: str,
        bucket: str,
        access_key_id: str,
        secret_access_key: str,
        url_ttl: int,
    ) -> None:
        options: dict[str, Any] = {
            "service_name": "s3",
            "region_name": region,
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "config": Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        }
        self.client = boto3.client(endpoint_url=endpoint_url, **options)
        self.signing_client = boto3.client(endpoint_url=public_endpoint_url, **options)
        self.bucket = bucket
        self.url_ttl = url_ttl

    async def store(self, path: Path, key: str, content_type: str) -> StoredArtifact:
        await asyncio.to_thread(
            self.client.upload_file,
            str(path),
            self.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
        return StoredArtifact(self.name, key, path.stat().st_size)

    def signed_url(self, key: str) -> str:
        return self.signing_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=self.url_ttl,
        )


@cache
def artifact_storage(storage: str | None = None) -> ArtifactStorage:
    if storage is None:
        return artifact_storage(os.getenv("PROBE_ARTIFACT_STORAGE", "local"))
    if storage == "local":
        return LocalArtifactStorage()
    if storage != "s3":
        raise ValueError(f"Unsupported artifact storage {storage!r}")

    endpoint = _required_env("S3_ENDPOINT_URL")
    return S3ArtifactStorage(
        endpoint_url=endpoint,
        public_endpoint_url=os.getenv("S3_PUBLIC_ENDPOINT_URL", endpoint),
        region=os.getenv("S3_REGION", "us-east-1"),
        bucket=_required_env("S3_BUCKET"),
        access_key_id=_required_env("S3_ACCESS_KEY_ID"),
        secret_access_key=_required_env("S3_SECRET_ACCESS_KEY"),
        url_ttl=int(os.getenv("S3_PRESIGNED_URL_TTL", "3600")),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required for S3 artifact storage")
    return value


@dataclass(frozen=True)
class ArtifactPaths:
    run: Path
    result: Path
    screenshot: Path
    trace: Path
    video: Path

    @classmethod
    def create(cls, root: Path, task_id: str) -> ArtifactPaths:
        run = root / task_id
        run.mkdir(parents=True, exist_ok=False)
        return cls(
            run=run,
            result=run / "result.json",
            screenshot=run / "screenshot.png",
            trace=run / "trace.zip",
            video=run / "replay.webm",
        )

    def write_result(self, data: dict[str, Any]) -> None:
        self.result.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
