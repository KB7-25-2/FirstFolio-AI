from mysql.connector.abstracts import MySQLConnectionAbstract

from app.core.config import Settings
from app.domain.document import DocumentMetadata
from app.infrastructure.database import create_mysql_connection


class DocumentNotFoundError(LookupError):
    pass


class MySQLDocumentRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(
        self,
        document: DocumentMetadata,
    ) -> int:
        self._validate_new_document(document)
        connection = create_mysql_connection(self._settings)

        try:
            document_id = self.create_in_transaction(
                connection=connection,
                document=document,
            )
            connection.commit()

            return document_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def create_in_transaction(
        self,
        connection: MySQLConnectionAbstract,
        document: DocumentMetadata,
    ) -> int:
        self._validate_new_document(document)
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO AI_DOCUMENTS (
                    document_type,
                    category,
                    title,
                    original_filename,
                    content_type,
                    s3_object_key,
                    s3_version_id,
                    source_url,
                    publisher,
                    published_at,
                    status,
                    error_message
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                """,
                (
                    document.document_type,
                    document.category,
                    document.title,
                    document.original_filename,
                    document.content_type,
                    document.s3_object_key,
                    document.s3_version_id,
                    document.source_url,
                    document.publisher,
                    document.published_at,
                    document.status,
                    document.error_message,
                ),
            )
            document_id = cursor.lastrowid

            if document_id is None:
                raise RuntimeError("생성된 MySQL document_id를 확인할 수 없습니다.")

            return int(document_id)
        finally:
            cursor.close()

    def find_by_id(
        self,
        document_id: int,
    ) -> DocumentMetadata:
        if document_id <= 0:
            raise ValueError("document_id는 양의 정수여야 합니다.")

        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    SELECT
                        document_id,
                        document_type,
                        category,
                        title,
                        original_filename,
                        content_type,
                        s3_object_key,
                        s3_version_id,
                        source_url,
                        publisher,
                        published_at,
                        status,
                        error_message,
                        created_at,
                        updated_at
                    FROM AI_DOCUMENTS
                    WHERE document_id = %s
                    """,
                    (document_id,),
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        finally:
            connection.close()

        if row is None:
            raise DocumentNotFoundError(f"문서를 찾을 수 없습니다: {document_id}")

        return self._row_to_document(row)

    def update_storage(
        self,
        document_id: int,
        s3_object_key: str,
        s3_version_id: str,
        status: str,
    ) -> None:
        connection = create_mysql_connection(self._settings)

        try:
            self.update_storage_in_transaction(
                connection=connection,
                document_id=document_id,
                s3_object_key=s3_object_key,
                s3_version_id=s3_version_id,
                status=status,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def update_storage_in_transaction(
        self,
        connection: MySQLConnectionAbstract,
        document_id: int,
        s3_object_key: str,
        s3_version_id: str,
        status: str,
    ) -> None:
        self._validate_storage_update(
            document_id=document_id,
            s3_object_key=s3_object_key,
            s3_version_id=s3_version_id,
            status=status,
        )
        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                UPDATE AI_DOCUMENTS
                SET
                    s3_object_key = %s,
                    s3_version_id = %s,
                    status = %s,
                    error_message = NULL
                WHERE document_id = %s
                """,
                (
                    s3_object_key,
                    s3_version_id,
                    status,
                    document_id,
                ),
            )

            if cursor.rowcount != 1:
                raise DocumentNotFoundError(f"문서를 찾을 수 없습니다: {document_id}")
        finally:
            cursor.close()

    @staticmethod
    def _validate_new_document(
        document: DocumentMetadata,
    ) -> None:
        if document.document_id is not None:
            raise ValueError("새 문서에는 document_id를 지정할 수 없습니다.")

        if not document.s3_object_key.strip():
            raise ValueError("s3_object_key는 비어 있을 수 없습니다.")

        if not document.s3_version_id.strip():
            raise ValueError("s3_version_id는 비어 있을 수 없습니다.")

    @staticmethod
    def _validate_storage_update(
        document_id: int,
        s3_object_key: str,
        s3_version_id: str,
        status: str,
    ) -> None:
        if document_id <= 0:
            raise ValueError("document_id는 양의 정수여야 합니다.")

        if not s3_object_key.strip():
            raise ValueError("s3_object_key는 비어 있을 수 없습니다.")

        if not s3_version_id.strip():
            raise ValueError("s3_version_id는 비어 있을 수 없습니다.")

        if not status.strip():
            raise ValueError("status는 비어 있을 수 없습니다.")

    @staticmethod
    def _row_to_document(
        row: tuple[object, ...],
    ) -> DocumentMetadata:
        return DocumentMetadata(
            document_id=int(row[0]),
            document_type=str(row[1]),
            category=None if row[2] is None else str(row[2]),
            title=str(row[3]),
            original_filename=str(row[4]),
            content_type=str(row[5]),
            s3_object_key=str(row[6]),
            s3_version_id=str(row[7]),
            source_url=None if row[8] is None else str(row[8]),
            publisher=None if row[9] is None else str(row[9]),
            published_at=row[10],
            status=str(row[11]),
            error_message=None if row[12] is None else str(row[12]),
            created_at=row[13],
            updated_at=row[14],
        )
