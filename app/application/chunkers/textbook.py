import re
from dataclasses import replace

from app.application.chunkers.merge import merge_short_chunks
from app.application.ports.document_chunker import DocumentChunker
from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument

_CHAPTER_PREFIX = chr(0xC81C)
_CHAPTER_SUFFIX = chr(0xC7A5)
_CHAPTER_HEADING_PATTERN = re.compile(
    rf"^(?:{_CHAPTER_PREFIX}\d+{_CHAPTER_SUFFIX}|[IVXLCDM]+\.)"
    r"\s+(?P<title>\S.*)$"
)
_SECTION_HEADING_PATTERN = re.compile(r"^(?:\d+\.\d+|\d+\.)\s+(?P<title>\S.*)$")
_SUBSECTION_HEADING_PATTERN = re.compile(r"^\d+\)\s+(?P<title>\S.*)$")


class TextbookChunker:
    def __init__(self, paragraph_chunker: DocumentChunker) -> None:
        self._paragraph_chunker = paragraph_chunker

    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        paragraph_chunks = self._paragraph_chunker.chunk(document)
        chunks: list[DocumentChunk] = []
        chapter_heading: str | None = None
        section_heading: str | None = None
        subsection_heading: str | None = None

        for chunk in paragraph_chunks:
            for line in chunk.content.splitlines():
                content = line.strip()

                if match := _CHAPTER_HEADING_PATTERN.fullmatch(content):
                    chapter_heading = match.group("title")
                    section_heading = None
                    subsection_heading = None
                elif match := _SECTION_HEADING_PATTERN.fullmatch(content):
                    section_heading = match.group("title")
                    subsection_heading = None
                elif match := _SUBSECTION_HEADING_PATTERN.fullmatch(content):
                    subsection_heading = match.group("title")

            heading = subsection_heading or section_heading or chapter_heading
            metadata = self._build_metadata(
                chapter_heading=chapter_heading,
                section_heading=section_heading,
                subsection_heading=subsection_heading,
            )
            chunks.append(replace(chunk, heading=heading, metadata=metadata))

        return merge_short_chunks(chunks)

    @staticmethod
    def _build_metadata(
        *,
        chapter_heading: str | None,
        section_heading: str | None,
        subsection_heading: str | None,
    ) -> dict[str, str] | None:
        metadata = {
            key: value
            for key, value in (
                ("chapter_heading", chapter_heading),
                ("section_heading", section_heading),
                ("subsection_heading", subsection_heading),
            )
            if value is not None
        }

        return metadata or None
