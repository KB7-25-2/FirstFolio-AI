from collections.abc import Sequence
from dataclasses import replace

from app.domain.chunk import DocumentChunk

_MIN_MERGEABLE_LENGTH = 50
_SENTENCE_ENDINGS = (".", "!", "?")


def merge_short_chunks(chunks: Sequence[DocumentChunk]) -> list[DocumentChunk]:
    """제목·목차처럼 문장으로 끝나지 않는 짧은 청크를 다음 청크에 합친다.

    50자 미만이면서 문장으로 끝나지 않는 청크는 검색 근거로 쓰기 어렵다.
    뒤따르는 청크에 이어 붙여 하나의 청크로 만들고, 문서 마지막까지 그런
    청크만 남으면 직전에 확정된 청크에 붙인다. heading·metadata는 병합된
    그룹의 마지막 청크 값을 쓴다 — 제목 전파 로직이 이미 그 값을 그룹 안
    모든 청크에 반영해 두었으므로 가장 구체적인 값이 마지막에 온다.
    이 과정에서 sequence·chunk_key는 병합 후 개수에 맞게 다시 매긴다.
    """
    if not chunks:
        return []

    groups: list[list[DocumentChunk]] = []
    pending: list[DocumentChunk] = []

    for chunk in chunks:
        pending.append(chunk)

        if not _should_merge_forward(chunk.content):
            groups.append(pending)
            pending = []

    if pending:
        if groups:
            groups[-1].extend(pending)
        else:
            groups.append(pending)

    merged_chunks: list[DocumentChunk] = []

    for sequence, group in enumerate(groups):
        anchor = group[0]
        last = group[-1]
        merged_chunks.append(
            replace(
                anchor,
                chunk_key=f"{anchor.document_id}:{sequence}",
                sequence=sequence,
                content="\n\n".join(chunk.content for chunk in group),
                heading=last.heading,
                metadata=last.metadata,
            )
        )

    return merged_chunks


def _should_merge_forward(content: str) -> bool:
    stripped = content.strip()
    return len(stripped) < _MIN_MERGEABLE_LENGTH and not stripped.endswith(
        _SENTENCE_ENDINGS
    )
