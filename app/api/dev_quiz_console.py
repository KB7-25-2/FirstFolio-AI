import html
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.application.quiz_batch import QuizBatchService
from app.domain.quiz import (
    QuestionType,
    QuizBatchRecord,
    QuizBatchRequestItem,
    QuizBatchStatus,
    QuizGenerationResult,
)
from app.quiz_batch_dry_run import write_jsonl
from app.quiz_mvp import create_quiz_generation_service

router = APIRouter(
    prefix="/api/v1/dev",
    tags=["development"],
)

_HISTORY_DIRECTORY = Path("data/local/quiz-generation-batches")

_STATUS_LABELS: dict[QuizBatchStatus, tuple[str, str]] = {
    QuizBatchStatus.SUCCEEDED: ("성공", "success"),
    QuizBatchStatus.FAILED: ("실패", "danger"),
    QuizBatchStatus.DUPLICATE: ("중복", "warning"),
}

_STYLE = """
body { font-family: -apple-system, sans-serif; margin: 2rem auto; max-width: 960px; color: #1a1a1a; }
h1 { font-size: 20px; }
h2 { font-size: 16px; margin-top: 2rem; }
.metrics { display: flex; gap: 12px; margin: 1rem 0; }
.metric { flex: 1; background: #f5f5f4; border-radius: 8px; padding: 12px 16px; }
.metric.tone-success { background: #e6f4ea; }
.metric.tone-danger { background: #fbe9e7; }
.metric.tone-warning { background: #fff4e0; }
.metric-label { font-size: 12px; color: #666; margin: 0 0 4px; }
.metric-value { font-size: 22px; font-weight: 600; margin: 0; }
.panel { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 8px; padding: 16px; }
.panel form { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap; }
.panel label { display: flex; flex-direction: column; font-size: 13px; color: #555; gap: 4px; }
.panel input, .panel select { padding: 6px 8px; font-size: 14px; }
.panel button { padding: 8px 16px; font-size: 14px; cursor: pointer; }
.entry { border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 8px; padding: 4px 12px; }
.entry summary { display: grid; grid-template-columns: 110px 110px 1fr 80px 100px 80px 1fr; gap: 8px; align-items: center; cursor: pointer; padding: 8px 0; }
.cell { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; text-align: center; }
.badge.tone-success { background: #e6f4ea; color: #1e7b34; }
.badge.tone-danger { background: #fbe9e7; color: #b3261e; }
.badge.tone-warning { background: #fff4e0; color: #8a5a00; }
.detail { padding: 8px 0 12px; border-top: 1px solid #eee; margin-top: 8px; font-size: 13px; }
.detail ul { margin: 4px 0 8px 20px; }
.detail li.correct { font-weight: 600; }
.empty { color: #777; }
"""


def get_quiz_batch_service(request: Request) -> QuizBatchService:
    generation_service = create_quiz_generation_service(request.app.state.settings)
    return QuizBatchService(generation_service)


def _read_history(
    directory: Path | None = None,
) -> list[tuple[float, QuizBatchRecord]]:
    target_directory = directory if directory is not None else _HISTORY_DIRECTORY

    if not target_directory.exists():
        return []

    entries: list[tuple[float, QuizBatchRecord]] = []

    for path in sorted(target_directory.glob("*.jsonl")):
        mtime = path.stat().st_mtime

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            entries.append((mtime, QuizBatchRecord.model_validate_json(line)))

    entries.sort(key=lambda entry: entry[0], reverse=True)

    return entries


@router.get("/quiz-console", response_class=HTMLResponse)
def render_quiz_console() -> HTMLResponse:
    return HTMLResponse(_render_page(_read_history()))


@router.get("/quiz-console/generate")
def generate_from_console(
    service: Annotated[QuizBatchService, Depends(get_quiz_batch_service)],
    question_type: str = Query(...),
    topic: str = Query(""),
) -> RedirectResponse:
    batch_run = service.generate(
        [QuizBatchRequestItem(question_type=question_type, topic=topic, count=1)]
    )
    output_path = _HISTORY_DIRECTORY / f"{batch_run.summary.batch_id}.jsonl"
    write_jsonl(output_path, batch_run.records)

    return RedirectResponse(url="/api/v1/dev/quiz-console", status_code=303)


def _render_page(entries: list[tuple[float, QuizBatchRecord]]) -> str:
    records = [record for _, record in entries]
    total = len(records)
    succeeded = sum(record.status == QuizBatchStatus.SUCCEEDED for record in records)
    failed = sum(record.status == QuizBatchStatus.FAILED for record in records)
    duplicates = sum(record.status == QuizBatchStatus.DUPLICATE for record in records)
    success_rate = round(succeeded / total * 100) if total else 0

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>퀴즈 생성 검수</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>퀴즈 생성 검수</h1>
<section class="metrics">
{_render_metric("총 생성 시도", total)}
{_render_metric("성공", succeeded, "success")}
{_render_metric("실패", failed, "danger")}
{_render_metric("중복", duplicates, "warning")}
{_render_metric("성공률", f"{success_rate}%")}
</section>
<section class="panel">
<h2>문제 생성</h2>
<form method="get" action="/api/v1/dev/quiz-console/generate">
<label>문제 유형
<select name="question_type">
{_render_question_type_options()}
</select>
</label>
<label>주제
<input type="text" name="topic" placeholder="정기 예금의 특징" required>
</label>
<button type="submit">생성</button>
</form>
</section>
<h2>생성 기록</h2>
{_render_history(entries)}
</body>
</html>
"""


def _render_metric(label: str, value: object, tone: str | None = None) -> str:
    tone_class = f" tone-{tone}" if tone else ""

    return (
        f'<div class="metric{tone_class}">'
        f'<p class="metric-label">{html.escape(label)}</p>'
        f'<p class="metric-value">{html.escape(str(value))}</p>'
        "</div>"
    )


def _render_question_type_options() -> str:
    return "".join(
        f'<option value="{question_type.value}">{question_type.value}</option>'
        for question_type in QuestionType
    )


def _render_history(entries: list[tuple[float, QuizBatchRecord]]) -> str:
    if not entries:
        return '<p class="empty">아직 생성한 문제가 없습니다.</p>'

    return "".join(_render_entry(mtime, record) for mtime, record in entries)


def _render_entry(mtime: float, record: QuizBatchRecord) -> str:
    label, tone = _STATUS_LABELS[record.status]
    generated_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    topic = html.escape(record.input.topic)
    question_type = html.escape(record.input.question_type)

    if record.status == QuizBatchStatus.SUCCEEDED and record.result is not None:
        execution = record.result.execution
        tokens = f"{execution.input_tokens} / {execution.output_tokens}"
        elapsed = f"{execution.elapsed_ms}ms"
        outcome = "근거검증 통과"
    else:
        tokens = "—"
        elapsed = "—"
        outcome = html.escape(record.error.reason) if record.error else ""

    summary = (
        "<summary>"
        f'<span class="cell time">{generated_at}</span>'
        f'<span class="cell type">{question_type}</span>'
        f'<span class="cell topic">{topic}</span>'
        f'<span class="badge tone-{tone}">{html.escape(label)}</span>'
        f'<span class="cell tokens">{tokens}</span>'
        f'<span class="cell elapsed">{elapsed}</span>'
        f'<span class="cell outcome">{outcome}</span>'
        "</summary>"
    )

    return f'<details class="entry">{summary}{_render_entry_detail(record)}</details>'


def _render_entry_detail(record: QuizBatchRecord) -> str:
    if record.status == QuizBatchStatus.SUCCEEDED and record.result is not None:
        return _render_quiz_detail(record.result)

    if record.error is None:
        return ""

    parts = [f"<p>{html.escape(record.error.reason)}</p>"]

    if record.error.errors:
        items = "".join(
            f"<li>{html.escape(error)}</li>" for error in record.error.errors
        )
        parts.append(f"<ul>{items}</ul>")

    if record.error.unsupported_claims:
        items = "".join(
            f"<li>{html.escape(claim)}</li>"
            for claim in record.error.unsupported_claims
        )
        parts.append(f"<p>근거로 확인할 수 없는 주장</p><ul>{items}</ul>")

    if record.duplicate is not None:
        parts.append(
            f"<p>이전 항목과 동일한 질문: {html.escape(record.duplicate.prompt)}</p>"
        )

    return f'<div class="detail">{"".join(parts)}</div>'


def _render_quiz_detail(result: QuizGenerationResult) -> str:
    quiz = result.quiz
    options = "".join(
        (
            '<li class="correct">'
            if option.option_id == quiz.correct_answer.option_id
            else "<li>"
        )
        + f"{html.escape(option.option_id)}. {html.escape(option.text)}</li>"
        for option in quiz.options
    )
    sources = "".join(
        f"<li>{html.escape(source.chunk_key)} — {html.escape(source.evidence_text)}</li>"
        for source in result.sources
    )

    return (
        '<div class="detail">'
        f"<p><strong>질문</strong> {html.escape(quiz.prompt)}</p>"
        f"<ul>{options}</ul>"
        f"<p><strong>해설</strong> {html.escape(quiz.explanation)}</p>"
        f"<p><strong>출처</strong></p><ul>{sources}</ul>"
        "</div>"
    )
