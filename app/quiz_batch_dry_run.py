import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from app.application.quiz_batch import QuizBatchRun, QuizBatchService
from app.core.config import Settings
from app.domain.quiz import QuizBatchInput, QuizBatchRecord, QuizBatchSummary
from app.quiz_mvp import create_quiz_generation_service

_DEFAULT_OUTPUT_DIRECTORY = Path("data/local/quiz-generation-batches")


def load_batch_input(input_path: Path) -> QuizBatchInput:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return QuizBatchInput.model_validate(payload)


def write_jsonl(
    output_path: Path,
    records: Sequence[QuizBatchRecord],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("x", encoding="utf-8") as output_file:
        for record in records:
            output_file.write(record.model_dump_json())
            output_file.write("\n")


def run_quiz_batch_dry_run(
    *,
    input_path: Path,
    output_path: Path | None = None,
    settings: Settings | None = None,
) -> QuizBatchSummary:
    batch_input = load_batch_input(input_path)

    if output_path is not None and output_path.exists():
        raise FileExistsError(f"출력 파일이 이미 존재합니다: {output_path}")

    runtime_settings = settings or Settings()
    generation_service = create_quiz_generation_service(runtime_settings)
    batch_run: QuizBatchRun = QuizBatchService(generation_service).generate(
        batch_input.items
    )
    resolved_output_path = output_path or (
        _DEFAULT_OUTPUT_DIRECTORY / f"{batch_run.summary.batch_id}.jsonl"
    )
    write_jsonl(resolved_output_path, batch_run.records)
    return batch_run.summary.model_copy(
        update={"output_path": str(resolved_output_path)}
    )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="퀴즈 생성 배치 Dry Run을 실행합니다.",
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        required=True,
        help="배치 입력 JSON 파일 경로",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        type=Path,
        help="결과 JSONL 파일 경로",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_argument_parser().parse_args(argv)

    try:
        summary = run_quiz_batch_dry_run(
            input_path=arguments.input_path,
            output_path=arguments.output_path,
        )
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as error:
        print(
            json.dumps(
                {
                    "stage": "batch_input",
                    "error": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(summary.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
