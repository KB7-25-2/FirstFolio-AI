import re

from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument

_NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?:[IVXLCDM]+\.|\d+\.|\d+\))\s+(?P<title>\S.*)$"
)


class ParagraphChunker:
    def chunk(
        self,
        document: SourceDocument,
        *,
        extract_textbook_headings: bool = False,
    ) -> list[DocumentChunk]:
        paragraphs: list[str] = []

        for paragraph in re.split(r"\n\s*\n", document.content):
            content = paragraph.strip()

            if content:
                paragraphs.append(content)

        chunks: list[DocumentChunk] = []
        current_heading: str | None = None

        for sequence, content in enumerate(paragraphs):
            if extract_textbook_headings:
                headings = [
                    match.group("title")
                    for line in content.splitlines()
                    if (match := _NUMBERED_HEADING_PATTERN.fullmatch(line.strip()))
                ]

                if headings:
                    current_heading = headings[-1]

            chunks.append(
                DocumentChunk(
                    document_id=document.document_id,
                    chunk_key=f"{document.document_id}:{sequence}",
                    sequence=sequence,
                    content=content,
                    title=document.title,
                    source=document.source,
                    heading=current_heading,
                )
            )

        return chunks
