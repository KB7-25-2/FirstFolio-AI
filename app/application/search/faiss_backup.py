from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from app.application.search.faiss_pipeline import FaissSearchPipeline
from app.core.config import Settings
from app.infrastructure.s3 import (
    download_binary_object,
    download_text_object,
    upload_binary_object,
    upload_text_object,
)


@dataclass(frozen=True)
class FaissBackupReference:
    index_object_key: str
    index_version_id: str
    mapping_object_key: str
    mapping_version_id: str


class FaissIndexBackupService:
    def __init__(
        self,
        settings: Settings,
        search_pipeline: FaissSearchPipeline,
    ) -> None:
        self._settings = settings
        self._search_pipeline = search_pipeline

    def backup(
        self,
        *,
        index_object_key: str,
        mapping_object_key: str,
    ) -> FaissBackupReference:
        with TemporaryDirectory(prefix="firstfolio-faiss-backup-") as directory:
            index_path = Path(directory) / "index.faiss"
            mapping_path = Path(directory) / "mapping.json"

            self._search_pipeline.save_index(
                index_path=index_path,
                mapping_path=mapping_path,
            )

            index_version_id = upload_binary_object(
                settings=self._settings,
                object_key=index_object_key,
                content=index_path.read_bytes(),
            )
            mapping_version_id = upload_text_object(
                settings=self._settings,
                object_key=mapping_object_key,
                content=mapping_path.read_bytes(),
            )

        return FaissBackupReference(
            index_object_key=index_object_key,
            index_version_id=index_version_id,
            mapping_object_key=mapping_object_key,
            mapping_version_id=mapping_version_id,
        )

    def restore(
        self,
        backup_reference: FaissBackupReference,
    ) -> None:
        index_content = download_binary_object(
            settings=self._settings,
            object_key=backup_reference.index_object_key,
            version_id=backup_reference.index_version_id,
        )
        mapping_content = download_text_object(
            settings=self._settings,
            object_key=backup_reference.mapping_object_key,
            version_id=backup_reference.mapping_version_id,
        )

        with TemporaryDirectory(prefix="firstfolio-faiss-restore-") as directory:
            index_path = Path(directory) / "index.faiss"
            mapping_path = Path(directory) / "mapping.json"
            index_path.write_bytes(index_content)
            mapping_path.write_bytes(mapping_content)

            self._search_pipeline.load_index(
                index_path=index_path,
                mapping_path=mapping_path,
            )
