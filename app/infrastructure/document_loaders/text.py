from pathlib import Path

from app.domain.document import SourceDocument


class UnsupportedDocumentFormatError(ValueError):
    """지원하지 않는 문서 형식일 때"""


class EmptyDocumentError(ValueError):
    """문서에 의미 있는 텍스트가 없을 때"""


class TextDocumentLoader:
    """텍스트 파일 또는 bytes를 문서 객체로 반환"""

    supported_suffix = ".txt"

    def load(self, path: str | Path, document_id: str) -> SourceDocument:
        file_path = Path(path)

        if not file_path.exists():
            raise FileNotFoundError(f"문서 파일을 찾을 수 없습니다: {file_path}")

        if not file_path.is_file():
            raise IsADirectoryError(f"문서 경로가 파일이 아닙니다: {file_path}")

        if file_path.suffix.lower() != self.supported_suffix:
            raise UnsupportedDocumentFormatError(
                f"지원하지 않는 문서 형식입니다: {file_path.suffix}"
            )

        content = file_path.read_text(encoding="utf-8")

        if not content.strip():
            raise EmptyDocumentError(f"문서에 내용이 없습니다: {file_path}")

        return SourceDocument(
            document_id=document_id,
            title=file_path.stem,
            content=content,
            source=str(file_path),
        )

    def load_bytes(
        self,
        content: bytes,
        document_id: str,
        title: str,
        source: str,
    ) -> SourceDocument:
        decoded_content = content.decode("utf-8")

        if not decoded_content.strip():
            raise EmptyDocumentError(f"문서에 내용이 없습니다: {source}")

        return SourceDocument(
            document_id=document_id,
            title=title,
            content=decoded_content,
            source=source,
        )
