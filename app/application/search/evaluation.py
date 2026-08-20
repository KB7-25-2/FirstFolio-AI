import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from app.domain.chunk import DocumentChunk
from app.domain.search import SearchEvaluationCase, SearchEvaluationMetrics

SearchMethod = Callable[[str, int], Sequence[str]]


def calculate_recall_at_k(
    case: SearchEvaluationCase,
    retrieved_chunk_keys: Sequence[str],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("평가할 상위 검색 결과 개수는 1 이상이어야 합니다.")

    if not case.relevant_chunk_keys:
        raise ValueError("평가 케이스에는 정답 청크 키가 하나 이상 필요합니다.")

    relevant_chunk_keys = set(case.relevant_chunk_keys)
    top_k_chunk_keys = set(retrieved_chunk_keys[:k])

    retrieved_relevant_count = len(relevant_chunk_keys & top_k_chunk_keys)

    return retrieved_relevant_count / len(relevant_chunk_keys)


def calculate_reciprocal_rank(
    case: SearchEvaluationCase,
    retrieved_chunk_keys: Sequence[str],
    k: int,
) -> float:
    if k < 1:
        raise ValueError("평가할 상위 검색 결과 개수는 1 이상이어야 합니다.")

    if not case.relevant_chunk_keys:
        raise ValueError("평가 케이스에는 정답 청크 키가 하나 이상 필요합니다.")

    relevant_chunk_keys = set(case.relevant_chunk_keys)

    for rank, chunk_key in enumerate(
        retrieved_chunk_keys[:k],
        start=1,
    ):
        if chunk_key in relevant_chunk_keys:
            return 1 / rank

    return 0.0


def evaluate_search_quality(
    cases: Sequence[SearchEvaluationCase],
    retrieved_chunk_keys_by_case: Sequence[Sequence[str]],
    k: int,
) -> SearchEvaluationMetrics:
    if not cases:
        raise ValueError("검색 품질을 평가할 케이스가 하나 이상 필요합니다.")

    if len(cases) != len(retrieved_chunk_keys_by_case):
        raise ValueError("평가 케이스 수와 검색 결과 목록 수가 일치해야 합니다.")

    recall_scores: list[float] = []
    reciprocal_ranks: list[float] = []

    for case, retrieved_chunk_keys in zip(
        cases,
        retrieved_chunk_keys_by_case,
        strict=True,
    ):
        recall_scores.append(
            calculate_recall_at_k(
                case=case,
                retrieved_chunk_keys=retrieved_chunk_keys,
                k=k,
            )
        )
        reciprocal_ranks.append(
            calculate_reciprocal_rank(
                case=case,
                retrieved_chunk_keys=retrieved_chunk_keys,
                k=k,
            )
        )

    return SearchEvaluationMetrics(
        top_k=k,
        evaluated_case_count=len(cases),
        recall_at_k=sum(recall_scores) / len(recall_scores),
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(reciprocal_ranks),
    )


def load_search_evaluation_cases(
    path: str | Path,
) -> tuple[SearchEvaluationCase, ...]:
    file_path = Path(path)

    if not file_path.is_file():
        raise FileNotFoundError(
            f"검색 평가 데이터 파일을 찾을 수 없습니다: {file_path}"
        )

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("검색 평가 데이터가 올바른 JSON 형식이 아닙니다.") from error

    if not isinstance(data, list) or not data:
        raise ValueError("검색 평가 데이터는 하나 이상의 객체 목록이어야 합니다.")

    cases: list[SearchEvaluationCase] = []

    for item in data:
        if not isinstance(item, dict):
            raise ValueError("검색 평가 항목은 객체 형식이어야 합니다.")

        query = item.get("query")
        relevant_chunk_keys = item.get("relevant_chunk_keys")
        relevant_text = item.get("relevant_text")

        if not isinstance(query, str) or not query.strip():
            raise ValueError("검색 평가 질문은 비어 있을 수 없습니다.")

        if (
            not isinstance(relevant_chunk_keys, list)
            or not relevant_chunk_keys
            or not all(
                isinstance(chunk_key, str) and chunk_key.strip()
                for chunk_key in relevant_chunk_keys
            )
        ):
            raise ValueError("검색 평가 항목에는 정답 청크 키가 하나 이상 필요합니다.")

        if relevant_text is not None and (
            not isinstance(relevant_text, str) or not relevant_text.strip()
        ):
            raise ValueError(
                "relevant_text를 지정하면 비어 있지 않은 문자열이어야 합니다."
            )

        cases.append(
            SearchEvaluationCase(
                query=query.strip(),
                relevant_chunk_keys=tuple(
                    chunk_key.strip() for chunk_key in relevant_chunk_keys
                ),
                relevant_text=(
                    relevant_text.strip() if relevant_text is not None else None
                ),
            )
        )

    return tuple(cases)


def find_chunk_key_by_text(
    chunks: Sequence[DocumentChunk],
    relevant_text: str,
) -> str | None:
    """정답 문장으로 청크를 다시 찾는다.

    청킹 방식을 바꾸면 chunk_key가 전부 바뀐다. 평가 케이스에 저장해 둔
    relevant_text로 새 코퍼스에서 같은 정답 청크를 다시 찾아
    relevant_chunk_keys를 갱신하는 데 사용한다. 일치하는 청크가 없으면
    None을 반환하며, 이 경우 해당 평가 케이스는 사람이 직접 확인해야 한다.
    """
    normalized_target = _normalize_for_match(relevant_text)

    if not normalized_target:
        raise ValueError("검색할 정답 문장은 비어 있을 수 없습니다.")

    for chunk in chunks:
        if normalized_target in _normalize_for_match(chunk.content):
            return chunk.chunk_key

    return None


def _normalize_for_match(text: str) -> str:
    return "".join(text.split())


def evaluate_search_methods(
    cases: Sequence[SearchEvaluationCase],
    search_methods: Mapping[str, SearchMethod],
    k: int,
) -> dict[str, SearchEvaluationMetrics]:
    metrics_by_method: dict[str, SearchEvaluationMetrics] = {}

    for method_name, search_method in search_methods.items():
        retrieved_chunk_keys_by_case = tuple(
            search_method(
                case.query,
                k,
            )
            for case in cases
        )
        metrics_by_method[method_name] = evaluate_search_quality(
            cases=cases,
            retrieved_chunk_keys_by_case=retrieved_chunk_keys_by_case,
            k=k,
        )

    return metrics_by_method
