from collections.abc import Callable
from datetime import datetime

from app.application.chunkers.paragraph import ParagraphChunker
from app.core.config import Settings
from app.domain.document import DocumentMetadata
from app.infrastructure.database import create_mysql_connection
from app.infrastructure.document_loaders.text import (
    EmptyDocumentError,
    TextDocumentLoader,
)
from app.infrastructure.repositories.mysql_chunk import MySQLChunkRepository
from app.infrastructure.repositories.mysql_document import MySQLDocumentRepository
from app.infrastructure.s3 import download_text_object, upload_text_object


class TextDocumentRegistrationPipeline:
    def __init__(
        self,
        settings: Settings,
        document_repository: MySQLDocumentRepository,
        chunk_repository: MySQLChunkRepository,
        index_invalidator: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._document_repository = document_repository
        self._chunk_repository = chunk_repository
        self._index_invalidator = index_invalidator
        self._loader = TextDocumentLoader()
        self._chunker = ParagraphChunker()

    def register(
        self,
        *,
        content: bytes,
        object_key: str,
        document_type: str,
        title: str,
        original_filename: str,
        category: str | None = None,
        source_url: str | None = None,
        publisher: str | None = None,
        published_at: datetime | None = None,
    ) -> tuple[int, int]:
        decoded_content = content.decode("utf-8")

        if not decoded_content.strip():
            raise EmptyDocumentError(f"문서에 내용이 없습니다: {original_filename}")

        version_id = upload_text_object(
            settings=self._settings,
            object_key=object_key,
            content=content,
        )
        stored_content = download_text_object(
            settings=self._settings,
            object_key=object_key,
            version_id=version_id,
        )

        connection = create_mysql_connection(self._settings)

        try:
            document_id = self._document_repository.create_in_transaction(
                connection=connection,
                document=DocumentMetadata(
                    document_type=document_type,
                    category=category,
                    title=title,
                    original_filename=original_filename,
                    content_type="text/plain",
                    s3_object_key=object_key,
                    s3_version_id=version_id,
                    source_url=source_url,
                    publisher=publisher,
                    published_at=published_at,
                    status="pending",
                ),
            )
            string_document_id = str(document_id)
            source_document = self._loader.load_bytes(
                content=stored_content,
                document_id=string_document_id,
                title=title,
                source=source_url or original_filename,
            )
            chunks = self._chunker.chunk(source_document)

            self._chunk_repository.replace_document_chunks_in_transaction(
                connection=connection,
                document_id=string_document_id,
                chunks=chunks,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        if self._index_invalidator is not None:
            self._index_invalidator()

        return document_id, len(chunks)
