"""원문 문서 도메인 모델"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceDocument:
    title: str
    content: str
    source: str
