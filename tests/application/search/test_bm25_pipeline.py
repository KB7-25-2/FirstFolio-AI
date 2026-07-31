from pathlib import Path

import pytest

from app.application.search.bm25_pipeline import (
    BM25SearchPipeline,
    SearchIndexNotBuiltError,
)
from app.core.config import Settings
from app.infrastructure.repositories.in_memory_chunk import (
    InMemoryChunkRepository,
)


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
    repository = InMemoryChunkRepository()
    pipeline = BM25SearchPipeline(
        settings,
        chunk_repository=repository,
    )

    chunk_count = pipeline.register_document(
        file_path,
        document_id="financial-guide",
    )
    indexed_chunk_count = pipeline.rebuild_index()
    results = pipeline.search("예금 금리")

    assert chunk_count == 4
    assert indexed_chunk_count == 4
    assert len(repository.find_all()) == 4
    assert len(results) == 1
    assert results[0].chunk.document_id == "financial-guide"
    assert results[0].chunk.chunk_key == "financial-guide:0"
    assert results[0].chunk.sequence == 0
    assert results[0].score > 0
    assert pipeline.search("부동산 임대") == []


def test_register_multiple_documents_before_rebuilding_index(
    tmp_path: Path,
) -> None:
    deposit_path = tmp_path / "deposit.txt"
    deposit_path.write_text(
        "예금은 돈을 맡기고 금리를 받는 금융상품이다.",
        encoding="utf-8",
    )

    tax_path = tmp_path / "tax.txt"
    tax_path.write_text(
        "세금은 국가에 납부하는 금액이다.",
        encoding="utf-8",
    )

    bond_path = tmp_path / "bond.txt"
    bond_path.write_text(
        "채권은 발행자에게 돈을 빌려주고 이자를 받는 상품이다.",
        encoding="utf-8",
    )

    settings = Settings(
        search_top_k=1,
        _env_file=None,
    )
    repository = InMemoryChunkRepository()
    pipeline = BM25SearchPipeline(
        settings,
        chunk_repository=repository,
    )

    pipeline.register_document(
        deposit_path,
        document_id="deposit",
    )
    pipeline.register_document(
        tax_path,
        document_id="tax",
    )
    pipeline.register_document(
        bond_path,
        document_id="bond",
    )

    with pytest.raises(
        SearchIndexNotBuiltError,
        match="rebuild_index",
    ):
        pipeline.search("예금 금리")

    indexed_chunk_count = pipeline.rebuild_index()

    assert indexed_chunk_count == 3
    assert len(repository.find_all()) == 3
    assert pipeline.search("예금 금리")[0].chunk.document_id == "deposit"
    assert pipeline.search("세금 납부")[0].chunk.document_id == "tax"

    with pytest.raises(FileNotFoundError):
        pipeline.register_document(
            tmp_path / "missing.txt",
            document_id="missing",
        )

    assert pipeline.search("예금 금리")[0].chunk.document_id == "deposit"


def test_replace_old_chunks_when_reindexing_document(
    tmp_path: Path,
) -> None:
    financial_path = tmp_path / "financial_guide.txt"
    financial_path.write_text(
        (
            "예금에 대한 설명.\n\n"
            "주식에 대한 설명.\n\n"
            "채권에 대한 설명.\n\n"
            "펀드에 대한 설명.\n\n"
            "보험과 보장에 대한 설명."
        ),
        encoding="utf-8",
    )

    tax_path = tmp_path / "tax_guide.txt"
    tax_path.write_text(
        "세금과 납부에 대한 설명.",
        encoding="utf-8",
    )

    settings = Settings(
        search_top_k=1,
        _env_file=None,
    )
    repository = InMemoryChunkRepository()
    pipeline = BM25SearchPipeline(
        settings,
        chunk_repository=repository,
    )

    pipeline.register_document(
        financial_path,
        document_id="financial-guide",
    )
    pipeline.register_document(
        tax_path,
        document_id="tax-guide",
    )
    pipeline.rebuild_index()

    assert pipeline.search("보험 보장")[0].chunk.chunk_key == "financial-guide:4"

    financial_path.write_text(
        (
            "예금에 대한 새로운 설명.\n\n"
            "주식에 대한 새로운 설명.\n\n"
            "채권에 대한 새로운 설명."
        ),
        encoding="utf-8",
    )

    chunk_count = pipeline.register_document(
        financial_path,
        document_id="financial-guide",
    )

    with pytest.raises(
        SearchIndexNotBuiltError,
        match="rebuild_index",
    ):
        pipeline.search("보험 보장")

    indexed_chunk_count = pipeline.rebuild_index()
    stored_chunks = repository.find_all()

    assert chunk_count == 3
    assert indexed_chunk_count == 4
    assert [chunk.chunk_key for chunk in stored_chunks] == [
        "financial-guide:0",
        "financial-guide:1",
        "financial-guide:2",
        "tax-guide:0",
    ]
    assert pipeline.search("보험 보장") == []
    assert pipeline.search("세금 납부")[0].chunk.document_id == "tax-guide"


def test_reject_search_before_building_index() -> None:
    settings = Settings(
        search_top_k=1,
        _env_file=None,
    )
    repository = InMemoryChunkRepository()
    pipeline = BM25SearchPipeline(
        settings,
        chunk_repository=repository,
    )

    with pytest.raises(
        SearchIndexNotBuiltError,
        match="rebuild_index",
    ):
        pipeline.search("예금")

    with pytest.raises(
        SearchIndexNotBuiltError,
        match="재생성할 문서 청크가 없습니다",
    ):
        pipeline.rebuild_index()
