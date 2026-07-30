from pathlib import Path

import pytest

from app.application.search.bm25_pipeline import (
    BM25SearchPipeline,
    SearchIndexNotBuiltError,
)
from app.core.config import Settings


def test_build_index_and_search(
    tmp_path: Path,
) -> None:
    file_path = tmp_path / "financial_guide.txt"
    file_path.write_text(
        (
            "예금은 돈을 맡기고 금리를 받는 금융상품이다.\n\n"
            "주식은 기업의 지분을 나타내는 금융상품이다.\n\n"
            "채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다.\n\n"
            "펀드는 여러 자산에 분산 투자하는 상품이다."
        ),
        encoding="utf-8",
    )

    settings = Settings(
        search_top_k=1,
        _env_file=None,
    )
    pipeline = BM25SearchPipeline(settings)

    chunk_count = pipeline.build_index(file_path)
    results = pipeline.search("예금 금리")

    assert chunk_count == 4
    assert len(results) == 1
    assert results[0].chunk.sequence == 0
    assert results[0].score > 0
    assert pipeline.search("부동산 임대") == []


def test_reject_search_before_building_index() -> None:
    settings = Settings(
        search_top_k=1,
        _env_file=None,
    )
    pipeline = BM25SearchPipeline(settings)

    with pytest.raises(
        SearchIndexNotBuiltError,
        match="문서 색인을 생성해야 합니다",
    ):
        pipeline.search("예금")
