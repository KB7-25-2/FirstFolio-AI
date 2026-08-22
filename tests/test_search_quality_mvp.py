import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app import search_quality_mvp
from app.application.search.index_health import SearchIndexMismatchError
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.search import SearchResult, VectorSearchResult


def create_chunk(chunk_key: str, title: str) -> DocumentChunk:
    document_id = chunk_key.split(":")[0]
    return DocumentChunk(
        document_id=document_id,
        chunk_key=chunk_key,
        sequence=0,
        content=f"{title} 설명",
        title=title,
        source=f"{document_id}.txt",
    )


def write_cases(tmp_path: Path) -> Path:
    file_path = tmp_path / "cases.json"
    file_path.write_text(
        json.dumps(
            [
                {
                    "query": "예금이란 무엇인가?",
                    "relevant_chunk_keys": ["deposit:0"],
                },
                {
                    "query": "주식이란 무엇인가?",
                    "relevant_chunk_keys": ["stock:0"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return file_path


def test_build_search_components_raises_when_index_mismatched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)
    repository = Mock()
    repository.find_all.return_value = [create_chunk("deposit:0", "예금")]
    faiss_search = Mock()
    faiss_search.vector_count = 999
    faiss_class = Mock()
    faiss_class.load.return_value = faiss_search

    monkeypatch.setattr(
        search_quality_mvp, "MySQLChunkRepository", Mock(return_value=repository)
    )
    monkeypatch.setattr(search_quality_mvp, "KiwiTokenizer", Mock())
    monkeypatch.setattr(search_quality_mvp, "BM25Search", Mock())
    monkeypatch.setattr(search_quality_mvp, "OpenAIEmbeddingClient", Mock())
    monkeypatch.setattr(search_quality_mvp, "FaissVectorSearch", faiss_class)

    with pytest.raises(SearchIndexMismatchError, match="corpus=1, faiss=999"):
        search_quality_mvp.build_search_components(settings)


def test_run_search_quality_report_measures_each_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deposit_chunk = create_chunk("deposit:0", "예금")
    stock_chunk = create_chunk("stock:0", "주식")

    bm25_search = Mock()
    bm25_search.search.side_effect = [
        [SearchResult(chunk=deposit_chunk, score=10.0)],
        [SearchResult(chunk=stock_chunk, score=8.0)],
    ]

    faiss_search = Mock()
    faiss_search.search.side_effect = [
        [VectorSearchResult(chunk_key="deposit:0", score=0.9)],
        [],
    ]

    hybrid_search = Mock()
    hybrid_search.search.side_effect = [
        [SearchResult(chunk=deposit_chunk, score=1.0)],
        [SearchResult(chunk=stock_chunk, score=1.0)],
    ]

    build_components = Mock(
        return_value=(Mock(), bm25_search, faiss_search, hybrid_search)
    )
    monkeypatch.setattr(search_quality_mvp, "build_search_components", build_components)

    report = search_quality_mvp.run_search_quality_report(
        cases_path=write_cases(tmp_path),
        settings=Settings(search_top_k=5, _env_file=None),
    )

    assert report["top_k"] == 5
    assert report["evaluated_case_count"] == 2
    assert report["search_quality"]["bm25"]["recall_at_k"] == pytest.approx(1.0)
    assert report["search_quality"]["faiss"]["recall_at_k"] == pytest.approx(0.5)
    assert report["search_quality"]["hybrid"]["recall_at_k"] == pytest.approx(1.0)
    assert "evidence_quality" not in report


def test_run_search_quality_report_includes_evidence_quality_when_topics_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deposit_chunk = DocumentChunk(
        document_id="deposit",
        chunk_key="deposit:0",
        sequence=0,
        content=(
            "주식을 거래하려면 증권회사에 계좌를 개설하고 주문을 위탁해야 한다. "
            "주문은 지정가와 시장가 방식으로 접수할 수 있다."
        ),
        title="예금",
        source="deposit.txt",
    )
    heading_chunk = DocumentChunk(
        document_id="deposit",
        chunk_key="deposit:1",
        sequence=1,
        content="3) 주식 거래 방법",
        title="예금",
        source="deposit.txt",
    )

    bm25_search = Mock()
    bm25_search.search.return_value = [
        SearchResult(chunk=deposit_chunk, score=10.0),
    ]
    faiss_search = Mock()
    faiss_search.search.return_value = []

    hybrid_search = Mock()
    hybrid_search.search.side_effect = [
        [SearchResult(chunk=deposit_chunk, score=1.0)],
        [],
        [
            SearchResult(chunk=deposit_chunk, score=1.0),
            SearchResult(chunk=heading_chunk, score=0.5),
        ],
    ]

    build_components = Mock(
        return_value=(Mock(), bm25_search, faiss_search, hybrid_search)
    )
    monkeypatch.setattr(search_quality_mvp, "build_search_components", build_components)

    report = search_quality_mvp.run_search_quality_report(
        cases_path=write_cases(tmp_path),
        topics=["주식 거래 절차"],
        settings=Settings(search_top_k=5, _env_file=None),
    )

    assert report["evidence_quality"] == [
        {
            "topic": "주식 거래 절차",
            "retrieved_count": 2,
            "usable_evidence_count": 1,
            "distinct_evidence_count": 2,
            "heading_fragment_count": 1,
        }
    ]


def test_load_topics_reads_json_array_of_strings(tmp_path: Path) -> None:
    file_path = tmp_path / "topics.json"
    file_path.write_text(
        json.dumps(["주식 거래 절차", "  예금과 적금의 차이  ", ""]),
        encoding="utf-8",
    )

    topics = search_quality_mvp.load_topics(file_path)

    assert topics == ("주식 거래 절차", "예금과 적금의 차이")


def test_load_topics_returns_empty_tuple_when_no_path_given() -> None:
    assert search_quality_mvp.load_topics(None) == ()


def test_reject_non_array_topics_file(tmp_path: Path) -> None:
    file_path = tmp_path / "topics.json"
    file_path.write_text(json.dumps({"not": "an array"}), encoding="utf-8")

    with pytest.raises(ValueError, match="topics 파일은 문자열 배열이어야 합니다."):
        search_quality_mvp.load_topics(file_path)


def test_print_report_as_json_and_write_to_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = {"top_k": 5, "search_quality": {}}
    run_report = Mock(return_value=report)
    monkeypatch.setattr(search_quality_mvp, "run_search_quality_report", run_report)
    output_path = tmp_path / "reports" / "result.json"

    exit_code = search_quality_mvp.main(
        [
            "--cases",
            "cases.json",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    printed = json.loads(captured.out)
    assert printed["top_k"] == 5
    assert printed["output_path"] == str(output_path)
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved == {"top_k": 5, "search_quality": {}}


def test_write_report_creates_parent_directories(tmp_path: Path) -> None:
    output_path = tmp_path / "nested" / "report.json"

    search_quality_mvp.write_report(output_path, {"top_k": 5})

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"top_k": 5}


def test_default_output_path_uses_evaluation_directory() -> None:
    output_path = search_quality_mvp.default_output_path()

    assert output_path.parent == Path("data/local/evaluation")
    assert output_path.name.startswith("search_quality_report_")
    assert output_path.suffix == ".json"


def test_print_error_and_return_failure_on_index_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_report = Mock(side_effect=SearchIndexMismatchError("corpus=1126, faiss=1018"))
    monkeypatch.setattr(search_quality_mvp, "run_search_quality_report", run_report)

    exit_code = search_quality_mvp.main(["--cases", "cases.json"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "corpus=1126, faiss=1018" in json.loads(captured.err)["error"]
