import re

from app.domain.chunk import DocumentChunk
from app.domain.document import SourceDocument


class ParagraphChunker:
    def chunk(self, document: SourceDocument) -> list[DocumentChunk]:
        paragraphs: list[str] = []

        for paragraph in re.split(r"\n\s*\n", document.content):
            content = paragraph.strip()

            if content:
                paragraphs.append(content)

        return [
            DocumentChunk(
                document_id=document.document_id,
                chunk_key=f"{document.document_id}:{sequence}",
                sequence=sequence,
                content=content,
                title=document.title,
                source=document.source,
            )
            for sequence, content in enumerate(paragraphs)
        ]
