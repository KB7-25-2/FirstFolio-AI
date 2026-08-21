import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from app.domain.quiz import QuizBatchRecord, QuizBatchStatus

_DEFAULT_OUTPUT_DIRECTORY = Path("data/local/evaluation")


def load_batch_records(path: Path) -> list[QuizBatchRecord]:
    if not path.is_file():
        raise FileNotFoundError(f"배치 결과 파일을 찾을 수 없습니다: {path}")

    records = [
        QuizBatchRecord.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    if not records:
        raise ValueError(f"배치 결과 파일에 레코드가 없습니다: {path}")

    return records


def summarize_batch(records: Sequence[QuizBatchRecord]) -> dict[str, object]:
    total = len(records)
    succeeded = [
        record for record in records if record.status == QuizBatchStatus.SUCCEEDED
    ]
    failed = [record for record in records if record.status == QuizBatchStatus.FAILED]
    duplicates = [
        record for record in records if record.status == QuizBatchStatus.DUPLICATE
    ]

    failure_by_stage = Counter(
        record.error.stage for record in failed if record.error is not None
    )
    failure_by_error_code = Counter(
        error_code
        for record in failed
        if record.error is not None
        for error_code in record.error.errors
    )
    grounding_not_supported_count = sum(
        1
        for record in failed
        if record.error is not None and "grounding_not_supported" in record.error.errors
    )
    duplicate_exact_count = sum(
        1
        for record in duplicates
        if record.error is not None and "duplicate_prompt" in record.error.errors
    )
    duplicate_semantic_count = sum(
        1
        for record in duplicates
        if record.error is not None
        and "semantic_duplicate_prompt" in record.error.errors
    )

    citations_total_by_topic: Counter[str] = Counter()
    succeeded_count_by_topic: Counter[str] = Counter()
    chunk_keys_by_topic: dict[str, set[str]] = {}

    for record in succeeded:
        if record.result is None:
            continue

        topic = record.input.topic
        succeeded_count_by_topic[topic] += 1
        citations_total_by_topic[topic] += len(record.result.quiz.citations)
        chunk_keys_by_topic.setdefault(topic, set()).update(
            citation.chunk_key for citation in record.result.quiz.citations
        )

    evidence_diversity_by_topic = {
        topic: {
            "succeeded_count": succeeded_count_by_topic[topic],
            "citations_total": citations_total_by_topic[topic],
            "distinct_chunk_keys": len(chunk_keys),
        }
        for topic, chunk_keys in chunk_keys_by_topic.items()
    }

    return {
        "total": total,
        "succeeded": len(succeeded),
        "failed": len(failed),
        "duplicates": len(duplicates),
        "success_rate": round(len(succeeded) / total, 4) if total else 0.0,
        "failure_by_stage": dict(failure_by_stage),
        "failure_by_error_code": dict(failure_by_error_code),
        "grounding_not_supported_count": grounding_not_supported_count,
        "grounding_not_supported_rate": (
            round(grounding_not_supported_count / total, 4) if total else 0.0
        ),
        "duplicate_exact_count": duplicate_exact_count,
        "duplicate_semantic_count": duplicate_semantic_count,
        "evidence_diversity_by_topic": evidence_diversity_by_topic,
    }


def build_report(
    *,
    input_path: Path,
    baseline_path: Path | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "input_path": str(input_path),
        "current": summarize_batch(load_batch_records(input_path)),
    }

    if baseline_path is not None:
        report["baseline_path"] = str(baseline_path)
        report["baseline"] = summarize_batch(load_batch_records(baseline_path))

    return report


def default_output_path() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_OUTPUT_DIRECTORY / f"quiz_batch_report_{timestamp}.json"


def write_report(
    output_path: Path,
    report: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="퀴즈 배치 JSONL 결과를 집계해 성공률·중복률·근거 다양성을 측정합니다.",
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        required=True,
        help="집계할 배치 결과 JSONL 파일 경로",
    )
    parser.add_argument(
        "--baseline",
        dest="baseline_path",
        type=Path,
        default=None,
        help="비교할 이전 배치 결과 JSONL 파일 경로 (선택)",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        default=None,
        help=(
            "결과 JSON 저장 경로 (기본값: "
            "data/local/evaluation/quiz_batch_report_<타임스탬프>.json)"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)

    try:
        report = build_report(
            input_path=arguments.input_path,
            baseline_path=arguments.baseline_path,
        )
    except (OSError, ValueError, FileNotFoundError) as error:
        print(
            json.dumps({"error": str(error)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1

    output_path = arguments.output_path or default_output_path()
    write_report(output_path, report)
    report["output_path"] = str(output_path)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
