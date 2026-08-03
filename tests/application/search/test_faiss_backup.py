from unittest.mock import Mock, patch

import pytest
from langchain_core.embeddings import DeterministicFakeEmbedding

from app.application.search.faiss_backup import (
    FaissBackupReference,
    FaissIndexBackupService,
)
from app.application.search.faiss_pipeline import FaissSearchPipeline
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.infrastructure.repositories.in_memory_chunk import InMemoryChunkRepository


def _pipeline() -> FaissSearchPipeline:
    repository = InMemoryChunkRepository()
    repository.save_all(
        [
            DocumentChunk(
                document_id="1",
                chunk_key="1:0",
                sequence=0,
                content="예금은 금리를 제공한다.",
                title="예금",
                source="financial.txt",
            ),
            DocumentChunk(
                document_id="1",
                chunk_key="1:1",
                sequence=1,
                content="채권은 만기와 이자를 가진다.",
                title="채권",
                source="financial.txt",
            ),
        ]
    )
    return FaissSearchPipeline(
        settings=Settings(
            search_top_k=2,
            _env_file=None,
        ),
        chunk_repository=repository,
        embedding_client=DeterministicFakeEmbedding(size=8),
    )


def test_backup_restore_and_search_same_results() -> None:
    settings = Settings(
        s3_bucket_name="test-rag-bucket",
        _env_file=None,
    )
    pipeline = _pipeline()
    pipeline.rebuild_index()
    original_results = pipeline.search("예금 금리")
    uploaded_objects: dict[tuple[str, str], bytes] = {}

    def upload_index(
        *,
        settings: Settings,
        object_key: str,
        content: bytes,
    ) -> str:
        assert settings.s3_bucket_name == "test-rag-bucket"
        version_id = "index-version-001"
        uploaded_objects[(object_key, version_id)] = content
        return version_id

    def upload_mapping(
        *,
        settings: Settings,
        object_key: str,
        content: bytes,
    ) -> str:
        assert settings.s3_bucket_name == "test-rag-bucket"
        version_id = "mapping-version-001"
        uploaded_objects[(object_key, version_id)] = content
        return version_id

    def download_index(
        *,
        settings: Settings,
        object_key: str,
        version_id: str,
    ) -> bytes:
        assert settings.s3_bucket_name == "test-rag-bucket"
        return uploaded_objects[(object_key, version_id)]

    def download_mapping(
        *,
        settings: Settings,
        object_key: str,
        version_id: str,
    ) -> bytes:
        assert settings.s3_bucket_name == "test-rag-bucket"
        return uploaded_objects[(object_key, version_id)]

    with (
        patch(
            "app.application.search.faiss_backup.upload_binary_object",
            side_effect=upload_index,
        ),
        patch(
            "app.application.search.faiss_backup.upload_text_object",
            side_effect=upload_mapping,
        ),
        patch(
            "app.application.search.faiss_backup.download_binary_object",
            side_effect=download_index,
        ),
        patch(
            "app.application.search.faiss_backup.download_text_object",
            side_effect=download_mapping,
        ),
    ):
        service = FaissIndexBackupService(
            settings=settings,
            search_pipeline=pipeline,
        )
        backup_reference = service.backup(
            index_object_key="indexes/financial/index.faiss",
            mapping_object_key="indexes/financial/mapping.json",
        )
        pipeline.invalidate_index()
        service.restore(backup_reference)

    restored_results = pipeline.search("예금 금리")

    assert backup_reference == FaissBackupReference(
        index_object_key="indexes/financial/index.faiss",
        index_version_id="index-version-001",
        mapping_object_key="indexes/financial/mapping.json",
        mapping_version_id="mapping-version-001",
    )
    assert [result.chunk_key for result in restored_results] == [
        result.chunk_key for result in original_results
    ]
    assert [result.score for result in restored_results] == pytest.approx(
        [result.score for result in original_results]
    )


@patch("app.application.search.faiss_backup.upload_binary_object")
def test_propagate_s3_upload_failure(
    upload_binary_mock: Mock,
) -> None:
    upload_binary_mock.side_effect = RuntimeError("S3 index upload failed")
    pipeline = _pipeline()
    pipeline.rebuild_index()
    service = FaissIndexBackupService(
        settings=Settings(
            s3_bucket_name="test-rag-bucket",
            _env_file=None,
        ),
        search_pipeline=pipeline,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 index upload failed",
    ):
        service.backup(
            index_object_key="indexes/financial/index.faiss",
            mapping_object_key="indexes/financial/mapping.json",
        )


@patch("app.application.search.faiss_backup.download_binary_object")
def test_propagate_s3_download_failure_without_loading_index(
    download_binary_mock: Mock,
) -> None:
    download_binary_mock.side_effect = RuntimeError("S3 index download failed")
    pipeline = Mock(spec=FaissSearchPipeline)
    service = FaissIndexBackupService(
        settings=Settings(
            s3_bucket_name="test-rag-bucket",
            _env_file=None,
        ),
        search_pipeline=pipeline,
    )

    with pytest.raises(
        RuntimeError,
        match="S3 index download failed",
    ):
        service.restore(
            FaissBackupReference(
                index_object_key="indexes/financial/index.faiss",
                index_version_id="index-version-001",
                mapping_object_key="indexes/financial/mapping.json",
                mapping_version_id="mapping-version-001",
            )
        )

    pipeline.load_index.assert_not_called()
