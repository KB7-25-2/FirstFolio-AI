import re
from dataclasses import replace

from app.application.ports.document_chunker import DocumentChunker
from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument

_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?:[IVXLCDM]+\.|\d+\.|\d+\))\s+(?P<title>\S.*)$"
)


class TextbookChunker:
    def __init__(self, paragraph_chunker: DocumentChunker) -> None:
        self._paragraph_chunker = paragraph_chunker

    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        paragraph_chunks = self._paragraph_chunker.chunk(document)
        chunks: list[DocumentChunk] = []
        current_heading: str | None = None

        for chunk in paragraph_chunks:
            headings = [
                match.group("title")
                for line in chunk.content.splitlines()
                if (match := _NUMBERED_HEADING_PATTERN.fullmatch(line.strip()))
            ]

            if headings:
                current_heading = headings[-1]

            chunks.append(replace(chunk, heading=current_heading))

        return chunks
