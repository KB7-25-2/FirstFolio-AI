import json
from collections.abc import Sequence

from mysql.connector.abstracts import MySQLConnectionAbstract

from app.application.ports.chunk_repository import ChunkNotFoundError
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.infrastructure.database import create_mysql_connection

_InsertRow = tuple[int, str, int, str, str | None, str, str | None]


class MySQLChunkRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def save_all(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        rows = self._build_insert_rows(chunks)

        if not rows:
            return

        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.executemany(
                    """
                    INSERT INTO AI_DOCUMENT_CHUNKS (
                        document_id,
                        chunk_key,
                        chunk_order,
                        chunk_type,
                        heading,
                        content,
                        metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
                connection.commit()
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def replace_document_chunks(
        self,
        document_id: str,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        numeric_document_id, rows = self._prepare_replacement(
            document_id=document_id,
            chunks=chunks,
        )
        connection = create_mysql_connection(self._settings)

        try:
            self._execute_chunk_replacement(
                connection=connection,
                document_id=numeric_document_id,
                rows=rows,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def replace_document_chunks_in_transaction(
        self,
        connection: MySQLConnectionAbstract,
        document_id: str,
        chunks: Sequence[DocumentChunk],
    ) -> None:
        numeric_document_id, rows = self._prepare_replacement(
            document_id=document_id,
            chunks=chunks,
        )
        self._execute_chunk_replacement(
            connection=connection,
            document_id=numeric_document_id,
            rows=rows,
        )

    def _prepare_replacement(
        self,
        document_id: str,
        chunks: Sequence[DocumentChunk],
    ) -> tuple[int, list[_InsertRow]]:
        numeric_document_id = self._parse_document_id(document_id)

        for chunk in chunks:
            if chunk.document_id != document_id:
                raise ValueError(
                    "교체할 청크의 document_id가 요청한 문서 ID와 다릅니다."
                )

        rows = self._build_insert_rows(chunks)

        return numeric_document_id, rows

    @staticmethod
    def _execute_chunk_replacement(
        connection: MySQLConnectionAbstract,
        document_id: int,
        rows: Sequence[_InsertRow],
    ) -> None:
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                DELETE FROM AI_DOCUMENT_CHUNKS
                WHERE document_id = %s
                """,
                (document_id,),
            )

            if rows:
                cursor.executemany(
                    """
                    INSERT INTO AI_DOCUMENT_CHUNKS (
                        document_id,
                        chunk_key,
                        chunk_order,
                        chunk_type,
                        heading,
                        content,
                        metadata_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    rows,
                )
        finally:
            cursor.close()

    def find_all(self) -> list[DocumentChunk]:
        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                        chunks.document_id,
                        chunks.chunk_key,
                        chunks.chunk_order,
                        chunks.content,
                        documents.title,
                        COALESCE(
                            documents.source_url,
                            documents.original_filename
                        ) AS source,
                        chunks.heading,
                        documents.source_url,
                        documents.published_at,
                        chunks.metadata_json
                    FROM AI_DOCUMENT_CHUNKS AS chunks
                    INNER JOIN AI_DOCUMENTS AS documents
                        ON documents.document_id = chunks.document_id
                    ORDER BY
                        chunks.document_id,
                        chunks.chunk_order
                    """
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
        finally:
            connection.close()

        return [self._row_to_chunk(row) for row in rows]

    def find_by_chunk_keys(
        self,
        chunk_keys: Sequence[str],
    ) -> list[DocumentChunk]:
        if not chunk_keys:
            return []

        placeholders = ", ".join(["%s"] * len(chunk_keys))
        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    f"""
                    SELECT
                        chunks.document_id,
                        chunks.chunk_key,
                        chunks.chunk_order,
                        chunks.content,
                        documents.title,
                        COALESCE(
                            documents.source_url,
                            documents.original_filename
                        ) AS source,
                        chunks.heading,
                        documents.source_url,
                        documents.published_at,
                        chunks.metadata_json
                    FROM AI_DOCUMENT_CHUNKS AS chunks
                    INNER JOIN AI_DOCUMENTS AS documents
                        ON documents.document_id = chunks.document_id
                    WHERE chunks.chunk_key IN ({placeholders})
                    """,
                    tuple(chunk_keys),
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()
        finally:
            connection.close()

        chunks_by_key = {
            chunk.chunk_key: chunk
            for chunk in (self._row_to_chunk(row) for row in rows)
        }
        missing_chunk_keys = [
            chunk_key for chunk_key in chunk_keys if chunk_key not in chunks_by_key
        ]

        if missing_chunk_keys:
            missing_keys = ", ".join(missing_chunk_keys)
            raise ChunkNotFoundError(f"요청한 청크를 찾을 수 없습니다: {missing_keys}")

        return [chunks_by_key[chunk_key] for chunk_key in chunk_keys]

    def _build_insert_rows(
        self,
        chunks: Sequence[DocumentChunk],
    ) -> list[_InsertRow]:
        rows: list[_InsertRow] = []

        for chunk in chunks:
            document_id = self._parse_document_id(chunk.document_id)
            expected_chunk_key = f"{document_id}:{chunk.sequence}"

            if chunk.chunk_key != expected_chunk_key:
                raise ValueError(
                    "chunk_key는 {document_id}:{chunk_order} 형식이어야 합니다."
                )

            rows.append(
                (
                    document_id,
                    chunk.chunk_key,
                    chunk.sequence,
                    "paragraph",
                    chunk.heading,
                    chunk.content,
                    json.dumps(chunk.metadata, ensure_ascii=False)
                    if chunk.metadata is not None
                    else None,
                )
            )

        return rows

    @staticmethod
    def _parse_document_id(document_id: str) -> int:
        try:
            numeric_document_id = int(document_id)
        except ValueError as error:
            raise ValueError(
                "MySQL document_id는 양의 정수 문자열이어야 합니다."
            ) from error

        if numeric_document_id <= 0 or str(numeric_document_id) != document_id:
            raise ValueError("MySQL document_id는 양의 정수 문자열이어야 합니다.")

        return numeric_document_id

    @staticmethod
    def _row_to_chunk(row: tuple[object, ...]) -> DocumentChunk:
        return DocumentChunk(
            document_id=str(row[0]),
            chunk_key=str(row[1]),
            sequence=int(row[2]),
            content=str(row[3]),
            title=str(row[4]),
            source=str(row[5]),
            heading=None if row[6] is None else str(row[6]),
            source_url=None if row[7] is None else str(row[7]),
            published_at=row[8],
            metadata=MySQLChunkRepository._parse_metadata(row[9]),
        )

    @staticmethod
    def _parse_metadata(value: object) -> dict[str, str] | None:
        if value is None:
            return None

        parsed = json.loads(value) if isinstance(value, str) else value

        if not isinstance(parsed, dict) or not all(
            isinstance(key, str) and isinstance(item, str)
            for key, item in parsed.items()
        ):
            raise ValueError(
                "metadata_json must contain an object with string keys and values."
            )

        return dict(parsed)
