from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from qa_agent.artifacts import LocalArtifactStorage, S3ArtifactStorage


@pytest.mark.asyncio
async def test_local_storage_keeps_existing_path(tmp_path: Path) -> None:
    replay = tmp_path / "replay.webm"
    replay.write_bytes(b"video")

    stored = await LocalArtifactStorage().store(
        replay, "runs/run-1/replay.webm", "video/webm"
    )

    assert stored.storage == "local"
    assert stored.key == str(replay)
    assert stored.size_bytes == 5


@pytest.mark.asyncio
async def test_s3_storage_uploads_and_signs(tmp_path: Path) -> None:
    replay = tmp_path / "replay.webm"
    replay.write_bytes(b"video")
    upload_client = Mock()
    signing_client = Mock()
    signing_client.generate_presigned_url.return_value = "http://minio/replay"

    with patch(
        "qa_agent.artifacts.boto3.client",
        side_effect=[upload_client, signing_client],
    ):
        storage = S3ArtifactStorage(
            endpoint_url="http://minio:9000",
            public_endpoint_url="http://localhost:9000",
            region="us-east-1",
            bucket="probe-artifacts",
            access_key_id="probe",
            secret_access_key="secret",
            url_ttl=60,
        )

    stored = await storage.store(replay, "runs/run-1/replay.webm", "video/webm")

    upload_client.upload_file.assert_called_once_with(
        str(replay),
        "probe-artifacts",
        "runs/run-1/replay.webm",
        ExtraArgs={"ContentType": "video/webm"},
    )
    assert stored.storage == "s3"
    assert storage.signed_url(stored.key) == "http://minio/replay"
