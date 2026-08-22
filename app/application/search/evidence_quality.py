import re
from collections.abc import Mapping, Sequence

from app.domain.chunk import DocumentChunk
from app.domain.search import EvidenceQualityMetrics

_MIN_USABLE_LENGTH = 50
_SENTENCE_ENDINGS = (".", "!", "?")
_HEADING_PATTERN = re.compile(
    r"^(?:제\d+장|[IVXLCDM]+\.|\d+(?:\.\d+)*\.?|\d+\)|[①-⑳])\s*"
)


def evaluate_evidence_quality(
    topic: str,
    retrieved_chunks: Sequence[DocumentChunk],
) -> EvidenceQualityMetrics:
    usable_evidence_count = sum(
        1 for chunk in retrieved_chunks if _is_usable(chunk.content)
    )
    heading_fragment_count = sum(
        1 for chunk in retrieved_chunks if _is_heading_fragment(chunk.content)
    )
    distinct_evidence_count = len(
        {_normalize_for_dedup(chunk.content) for chunk in retrieved_chunks}
    )

    return EvidenceQualityMetrics(
        topic=topic,
        retrieved_count=len(retrieved_chunks),
        usable_evidence_count=usable_evidence_count,
        distinct_evidence_count=distinct_evidence_count,
        heading_fragment_count=heading_fragment_count,
    )


def evaluate_evidence_quality_for_topics(
    retrieved_chunks_by_topic: Mapping[str, Sequence[DocumentChunk]],
) -> list[EvidenceQualityMetrics]:
    return [
        evaluate_evidence_quality(
            topic=topic,
            retrieved_chunks=retrieved_chunks,
        )
        for topic, retrieved_chunks in retrieved_chunks_by_topic.items()
    ]


def _is_usable(content: str) -> bool:
    stripped = content.strip()
    return len(stripped) >= _MIN_USABLE_LENGTH and stripped.endswith(_SENTENCE_ENDINGS)


def _is_heading_fragment(content: str) -> bool:
    stripped = content.strip()
    return bool(_HEADING_PATTERN.match(stripped)) or not stripped.endswith(
        _SENTENCE_ENDINGS
    )


def _normalize_for_dedup(content: str) -> str:
    return "".join(content.split())
