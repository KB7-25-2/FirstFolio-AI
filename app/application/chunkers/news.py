from collections.abc import Sequence

from app.application.ports.document_chunker import DocumentChunker
from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument

_HEADER_FIELDS = (
    ("문서유형", "document_type"),
    ("제목", "title"),
    ("언론사", "publisher"),
    ("카테고리", "category"),
    ("작성자", "author"),
    ("발행일", "published_at"),
    ("기준시점", "reference_at"),
    ("수집일", "collected_at"),
    ("기사 ID", "article_id"),
    ("원문 URL", "source_url"),
    ("본문 형태", "body_type"),
)
_NEWS_DOCUMENT_TYPE = "뉴스"
_SECTION_HEADINGS = (
    "핵심 내용",
    "키워드",
    "출처 유의사항",
)


class InvalidNewsDocumentError(ValueError):
    pass


class NewsChunker:
    def __init__(
        self,
        paragraph_chunker: DocumentChunker,
        max_chars: int = 2000,
    ) -> None:
        if max_chars <= 0:
            raise ValueError("max_chars must be greater than zero.")

        self._paragraph_chunker = paragraph_chunker
        self._max_chars = max_chars

    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        paragraph_chunks = self._paragraph_chunker.chunk(document)

        if not paragraph_chunks:
            raise InvalidNewsDocumentError("News header is missing.")

        paragraphs = [chunk.content for chunk in paragraph_chunks]
        metadata = self._parse_header(paragraphs[0])
        section_indices = self._validate_sections(paragraphs)
        full_content = document.content.strip()

        if len(full_content) <= self._max_chars:
            return [
                self._build_chunk(
                    document=document,
                    sequence=0,
                    content=full_content,
                    heading=None,
                    metadata=metadata,
                )
            ]

        chunks: list[DocumentChunk] = []
        section_starts = (0, section_indices[1], section_indices[2])
        section_ends = (section_indices[1], section_indices[2], len(paragraphs))

        for section_index, (start, end) in enumerate(
            zip(section_starts, section_ends, strict=True)
        ):
            heading = _SECTION_HEADINGS[section_index]
            section_paragraphs = paragraphs[start:end]
            leading_count = 3 if section_index == 0 else 2

            for content in self._pack_section(section_paragraphs, leading_count):
                chunk_metadata = {**metadata, "section": heading}
                chunks.append(
                    self._build_chunk(
                        document=document,
                        sequence=len(chunks),
                        content=content,
                        heading=heading,
                        metadata=chunk_metadata,
                    )
                )

        return chunks

    @staticmethod
    def _parse_header(header: str) -> dict[str, str]:
        lines = header.splitlines()

        if len(lines) != len(_HEADER_FIELDS):
            raise InvalidNewsDocumentError(
                "News header must contain all fields in the required order."
            )

        metadata: dict[str, str] = {}

        for line, (expected_label, metadata_key) in zip(
            lines, _HEADER_FIELDS, strict=True
        ):
            label, separator, value = line.partition(":")
            normalized_value = value.strip()

            if (
                separator != ":"
                or label.strip() != expected_label
                or not normalized_value
            ):
                raise InvalidNewsDocumentError(
                    "News header must contain all fields in the required order."
                )

            metadata[metadata_key] = normalized_value

        if metadata["document_type"] != _NEWS_DOCUMENT_TYPE:
            raise InvalidNewsDocumentError("News header document type must be news.")

        return metadata

    @staticmethod
    def _validate_sections(paragraphs: Sequence[str]) -> tuple[int, int, int]:
        indices: list[int] = []

        for heading in _SECTION_HEADINGS:
            matches = [
                index
                for index, paragraph in enumerate(paragraphs)
                if paragraph == heading
            ]

            if len(matches) != 1:
                raise InvalidNewsDocumentError(
                    "News sections must appear once in the required order."
                )

            indices.append(matches[0])

        if indices[0] != 1 or indices != sorted(indices):
            raise InvalidNewsDocumentError(
                "News sections must appear once in the required order."
            )

        if indices[1] - indices[0] < 2 or indices[2] - indices[1] < 2:
            raise InvalidNewsDocumentError("Each news section must contain content.")

        if indices[2] >= len(paragraphs) - 1:
            raise InvalidNewsDocumentError("Each news section must contain content.")

        return indices[0], indices[1], indices[2]

    def _pack_section(
        self,
        paragraphs: Sequence[str],
        leading_count: int,
    ) -> list[str]:
        packed = ["\n\n".join(paragraphs[:leading_count])]

        for paragraph in paragraphs[leading_count:]:
            candidate = f"{packed[-1]}\n\n{paragraph}"

            if len(candidate) <= self._max_chars:
                packed[-1] = candidate
            else:
                packed.append(paragraph)

        return packed

    @staticmethod
    def _build_chunk(
        *,
        document: SourceDocument,
        sequence: int,
        content: str,
        heading: str | None,
        metadata: dict[str, str],
    ) -> DocumentChunk:
        return DocumentChunk(
            document_id=document.document_id,
            chunk_key=f"{document.document_id}:{sequence}",
            sequence=sequence,
            content=content,
            title=document.title,
            source=document.source,
            heading=heading,
            metadata=dict(metadata),
        )
