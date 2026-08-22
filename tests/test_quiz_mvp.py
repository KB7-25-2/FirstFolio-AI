import json
from unittest.mock import Mock

import pytest

from app import quiz_mvp
from app.application.quiz_generation import QuizGenerationValidationError
from app.core.config import Settings
from app.domain.chunk import DocumentChunk
from app.domain.quiz import (
    GroundingValidation,
    QuestionType,
    Quiz,
    QuizExecution,
    QuizGenerationResult,
    QuizSource,
    QuizValidation,
)


def _quiz_result() -> QuizGenerationResult:
    return QuizGenerationResult(
        quiz=Quiz.model_validate(
            {
                "usage_type": "SUB_CHAPTER",
                "question_type": "SINGLE_CHOICE",
                "prompt": "예금에 대한 설명으로 옳은 것은?",
                "scenario_json": None,
                "options": [
                    {"option_id": "1", "text": "선택지 1"},
                    {"option_id": "2", "text": "선택지 2"},
                    {"option_id": "3", "text": "선택지 3"},
                    {"option_id": "4", "text": "선택지 4"},
                ],
                "correct_answer": {"option_id": "1"},
                "explanation": "예금은 금융기관에 돈을 맡기는 상품이다.",
                "difficulty": "EASY",
                "citations": [
                    {
                        "chunk_key": "47:0",
                        "evidence_text": "예금은 금융기관에 돈을 맡기는 상품이다.",
                    }
                ],
            }
        ),
        sources=[
            QuizSource(
                document_id=47,
                chunk_key="47:0",
                title="금융 교과서",
                heading="저축과 저축 상품",
                source_url=None,
                published_at=None,
                evidence_text="예금은 금융기관에 돈을 맡기는 상품이다.",
            )
        ],
        validation=QuizValidation(
            schema_valid=True,
            answer_valid=True,
            citation_valid=True,
            grounded=True,
            duplicate=False,
            errors=[],
        ),
        execution=QuizExecution(
            model="gpt-4o-mini",
            input_tokens=120,
            output_tokens=80,
            elapsed_ms=250,
        ),
    )


@pytest.mark.parametrize(
    ("quiz_type", "question_type"),
    [
        ("true_false", QuestionType.TRUE_FALSE),
        ("single_choice", QuestionType.SINGLE_CHOICE),
        ("scenario", QuestionType.SCENARIO),
    ],
)
def test_map_cli_quiz_type_to_domain_type(
    quiz_type: str,
    question_type: QuestionType,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(_env_file=None)
    service = Mock()
    service.generate.return_value = _quiz_result()
    create_service = Mock(return_value=service)
    monkeypatch.setattr(
        quiz_mvp,
        "create_quiz_generation_service",
        create_service,
    )

    result = quiz_mvp.generate_quiz_mvp(
        quiz_type=quiz_type,
        topic="예금",
        settings=settings,
    )

    assert result == _quiz_result()
    create_service.assert_called_once_with(settings)
    service.generate.assert_called_once_with(
        question_type=question_type,
        topic="예금",
    )


def test_reject_unsupported_quiz_type() -> None:
    with pytest.raises(ValueError, match="지원하지 않는 퀴즈 유형"):
        quiz_mvp.generate_quiz_mvp(
            quiz_type="multiple_choice",
            topic="예금",
            settings=Settings(_env_file=None),
        )


def test_create_service_with_mysql_and_search_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        embedding_model="text-embedding-test",
        generation_model="gpt-test",
        openai_timeout_seconds=45.0,
        openai_max_retries=3,
        faiss_index_path="/tmp/test.faiss",
        faiss_mapping_path="/tmp/test-mapping.json",
        _env_file=None,
    )
    chunk = DocumentChunk(
        document_id="47",
        chunk_key="47:0",
        sequence=0,
        content="예금은 금융상품이다.",
        title="금융 교과서",
        source="financial_textbook.txt",
    )
    repository = Mock()
    repository.find_all.return_value = [chunk]
    mysql_repository = Mock(return_value=repository)
    tokenizer = Mock()
    create_tokenizer = Mock(return_value=tokenizer)
    bm25_search = Mock()
    create_bm25 = Mock(return_value=bm25_search)
    embedding_client = Mock()
    create_embedding = Mock(return_value=embedding_client)
    faiss_search = Mock()
    faiss_search.vector_count = 1
    faiss_class = Mock()
    faiss_class.load.return_value = faiss_search
    hybrid_search = Mock()
    create_hybrid = Mock(return_value=hybrid_search)
    model_client = Mock()
    create_model_client = Mock(return_value=model_client)
    service = Mock()
    create_service = Mock(return_value=service)

    monkeypatch.setattr(quiz_mvp, "MySQLChunkRepository", mysql_repository)
    monkeypatch.setattr(quiz_mvp, "KiwiTokenizer", create_tokenizer)
    monkeypatch.setattr(quiz_mvp, "BM25Search", create_bm25)
    monkeypatch.setattr(quiz_mvp, "OpenAIEmbeddingClient", create_embedding)
    monkeypatch.setattr(quiz_mvp, "FaissVectorSearch", faiss_class)
    monkeypatch.setattr(quiz_mvp, "HybridSearch", create_hybrid)
    monkeypatch.setattr(quiz_mvp, "OpenAIQuizModelClient", create_model_client)
    monkeypatch.setattr(quiz_mvp, "QuizGenerationService", create_service)

    result = quiz_mvp.create_quiz_generation_service(settings)

    assert result is service
    mysql_repository.assert_called_once_with(settings)
    repository.find_all.assert_called_once_with()
    create_bm25.assert_called_once_with(chunks=[chunk], tokenizer=tokenizer)
    create_embedding.assert_called_once_with(
        model="text-embedding-test",
        timeout_seconds=45.0,
        max_retries=3,
    )
    faiss_class.load.assert_called_once_with(
        index_path=settings.faiss_index_path,
        mapping_path=settings.faiss_mapping_path,
        embedding_client=embedding_client,
    )
    create_hybrid.assert_called_once_with(
        settings=settings,
        bm25_search=bm25_search,
        faiss_search=faiss_search,
        chunk_repository=repository,
    )
    create_model_client.assert_called_once_with(
        model="gpt-test",
        timeout_seconds=45.0,
        max_retries=3,
    )
    create_service.assert_called_once_with(
        settings=settings,
        hybrid_search=hybrid_search,
        chunk_repository=repository,
        model_client=model_client,
        embedding_client=embedding_client,
    )


def test_warn_to_stderr_when_faiss_index_does_not_match_corpus(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    settings = Settings(
        faiss_index_path="/tmp/test.faiss",
        faiss_mapping_path="/tmp/test-mapping.json",
        _env_file=None,
    )
    chunk = DocumentChunk(
        document_id="47",
        chunk_key="47:0",
        sequence=0,
        content="예금은 금융상품이다.",
        title="금융 교과서",
        source="financial_textbook.txt",
    )
    repository = Mock()
    repository.find_all.return_value = [chunk]
    faiss_search = Mock()
    faiss_search.vector_count = 999
    faiss_class = Mock()
    faiss_class.load.return_value = faiss_search

    monkeypatch.setattr(quiz_mvp, "MySQLChunkRepository", Mock(return_value=repository))
    monkeypatch.setattr(quiz_mvp, "KiwiTokenizer", Mock())
    monkeypatch.setattr(quiz_mvp, "BM25Search", Mock())
    monkeypatch.setattr(quiz_mvp, "OpenAIEmbeddingClient", Mock())
    monkeypatch.setattr(quiz_mvp, "FaissVectorSearch", faiss_class)
    monkeypatch.setattr(quiz_mvp, "HybridSearch", Mock())
    monkeypatch.setattr(quiz_mvp, "OpenAIQuizModelClient", Mock())
    monkeypatch.setattr(quiz_mvp, "QuizGenerationService", Mock())

    quiz_mvp.create_quiz_generation_service(settings)

    warning = json.loads(capsys.readouterr().err)
    assert warning["warning"] == "faiss_index_corpus_mismatch"
    assert warning["corpus_chunk_count"] == 1
    assert warning["faiss_vector_count"] == 999


def test_print_success_result_as_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generate = Mock(return_value=_quiz_result())
    monkeypatch.setattr(quiz_mvp, "generate_quiz_mvp", generate)

    exit_code = quiz_mvp.main(
        [
            "--type",
            "single_choice",
            "--topic",
            "예금",
        ]
    )

    captured = capsys.readouterr()
    output = json.loads(captured.out)
    assert exit_code == 0
    assert captured.err == ""
    assert output["quiz"]["question_type"] == "SINGLE_CHOICE"
    assert output["validation"]["grounded"] is True
    assert output["execution"]["model"] == "gpt-4o-mini"
    generate.assert_called_once_with(
        quiz_type="single_choice",
        topic="예금",
    )


def test_print_validation_error_and_return_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    generate = Mock(
        side_effect=QuizGenerationValidationError(
            ["grounding_not_supported"],
            stage="grounding_validation",
            grounding_validation=GroundingValidation(
                supported=False,
                reason="선택지 2번의 금리 설명을 근거에서 확인할 수 없다.",
                unsupported_claims=["선택지 2번의 금리 설명"],
            ),
        )
    )
    monkeypatch.setattr(quiz_mvp, "generate_quiz_mvp", generate)

    exit_code = quiz_mvp.main(
        [
            "--type",
            "scenario",
            "--topic",
            "분산 투자",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "errors": ["grounding_not_supported"],
        "diagnostics": {
            "stage": "grounding_validation",
            "reason": "선택지 2번의 금리 설명을 근거에서 확인할 수 없다.",
            "unsupported_claims": ["선택지 2번의 금리 설명"],
        },
    }
