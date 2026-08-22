import pytest

from app.application.search.index_health import (
    SearchIndexMismatchError,
    check_index_matches_corpus,
    ensure_index_matches_corpus,
)


def test_check_reports_match_when_counts_are_equal() -> None:
    check = check_index_matches_corpus(
        corpus_chunk_count=10,
        faiss_vector_count=10,
    )

    assert check.matches is True


def test_check_reports_mismatch_when_counts_differ() -> None:
    check = check_index_matches_corpus(
        corpus_chunk_count=1126,
        faiss_vector_count=1018,
    )

    assert check.matches is False
    assert check.corpus_chunk_count == 1126
    assert check.faiss_vector_count == 1018


def test_ensure_does_not_raise_when_counts_match() -> None:
    ensure_index_matches_corpus(
        corpus_chunk_count=10,
        faiss_vector_count=10,
    )


def test_ensure_raises_when_counts_differ() -> None:
    with pytest.raises(
        SearchIndexMismatchError,
        match="corpus=1126, faiss=1018",
    ):
        ensure_index_matches_corpus(
            corpus_chunk_count=1126,
            faiss_vector_count=1018,
        )
