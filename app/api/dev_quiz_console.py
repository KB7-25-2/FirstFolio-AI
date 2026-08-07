import html
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

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
from app.infrastructure.repositories.mysql_quiz_prompt import MySQLQuizPromptRepository
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

_CATEGORIES = ["예·적금", "채권", "주식", "펀드"]
_QUESTION_TYPES = [qt.value for qt in QuestionType]

_INPUT_TOKEN_PRICE_USD = 0.15 / 1_000_000
_OUTPUT_TOKEN_PRICE_USD = 0.60 / 1_000_000

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
.panel input[type=number] { width: 64px; }
.panel button { padding: 8px 16px; font-size: 14px; cursor: pointer; }
.batch { border: 1px solid #c8d8e8; border-radius: 8px; margin-bottom: 12px; background: #f0f6ff; }
.batch > summary { display: grid; grid-template-columns: 140px 1fr 90px 100px 110px 100px; gap: 8px; align-items: center; cursor: pointer; padding: 10px 14px; font-size: 13px; font-weight: 500; }
.batch-items { padding: 0 12px 12px; }
.entry { border: 1px solid #e0e0e0; border-radius: 6px; margin-bottom: 8px; padding: 4px 12px; background: #fff; }
.entry summary { display: grid; grid-template-columns: 110px 110px 1fr 80px 170px 80px 1fr; gap: 8px; align-items: center; cursor: pointer; padding: 8px 0; }
.cell { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.badge { font-size: 12px; padding: 2px 8px; border-radius: 4px; text-align: center; }
.badge.tone-success { background: #e6f4ea; color: #1e7b34; }
.badge.tone-danger { background: #fbe9e7; color: #b3261e; }
.badge.tone-warning { background: #fff4e0; color: #8a5a00; }
.detail { padding: 8px 0 12px; border-top: 1px solid #eee; margin-top: 8px; font-size: 13px; }
.detail ul { margin: 4px 0 8px 20px; }
.detail li.correct { color: #b3261e; }
.empty { color: #777; }
.batch-filter { display: flex; gap: 12px; align-items: flex-end; margin-bottom: 10px; }
.batch-filter label { display: flex; flex-direction: column; font-size: 12px; color: #555; gap: 4px; }
.batch-filter select { padding: 4px 6px; font-size: 13px; }
"""

_SCRIPT = """
function filterBatchItems(batchId) {
  var type = document.getElementById('qtype-' + batchId).value;
  var topic = document.getElementById('topic-' + batchId).value;
  var items = document.getElementById('items-' + batchId).querySelectorAll('.entry');
  items.forEach(function (item) {
    var matchesType = !type || item.dataset.questionType === type;
    var matchesTopic = !topic || item.dataset.topic === topic;
    item.style.display = (matchesType && matchesTopic) ? '' : 'none';
  });
}
"""


@dataclass
class _BatchGroup:
    batch_id: UUID
    mtime: float
    records: list[QuizBatchRecord] = field(default_factory=list)


def get_quiz_batch_service(request: Request) -> QuizBatchService:
    settings = request.app.state.settings
    generation_service = create_quiz_generation_service(settings)
    prompt_repository = MySQLQuizPromptRepository(settings)
    return QuizBatchService(generation_service, prompt_repository=prompt_repository)


def _read_history(
    directory: Path | None = None,
) -> list[_BatchGroup]:
    target_directory = directory if directory is not None else _HISTORY_DIRECTORY

    if not target_directory.exists():
        return []

    groups: dict[UUID, _BatchGroup] = {}
    mtime_by_batch: dict[UUID, float] = {}

    for path in sorted(target_directory.glob("*.jsonl")):
        mtime = path.stat().st_mtime

        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue

            record = QuizBatchRecord.model_validate_json(line)
            bid = record.batch_id

            if bid not in groups:
                groups[bid] = _BatchGroup(batch_id=bid, mtime=mtime)
                mtime_by_batch[bid] = mtime

            groups[bid].records.append(record)

    result = list(groups.values())
    result.sort(key=lambda g: g.mtime, reverse=True)

    return result


@router.get("/quiz-console", response_class=HTMLResponse)
def render_quiz_console() -> HTMLResponse:
    return HTMLResponse(_render_page(_read_history()))


@router.get("/quiz-console/generate")
def generate_from_console(
    service: Annotated[QuizBatchService, Depends(get_quiz_batch_service)],
    question_type: str = Query(...),
    topic: str = Query(""),
    count: int = Query(1, ge=1, le=100),
) -> RedirectResponse:
    if topic == "랜덤" or question_type == "랜덤":
        items = [
            QuizBatchRequestItem(
                question_type=random.choice(_QUESTION_TYPES)
                if question_type == "랜덤"
                else question_type,
                topic=random.choice(_CATEGORIES) if topic == "랜덤" else topic,
                count=1,
            )
            for _ in range(count)
        ]
    else:
        items = [
            QuizBatchRequestItem(question_type=question_type, topic=topic, count=count)
        ]
    batch_run = service.generate(items)
    output_path = _HISTORY_DIRECTORY / f"{batch_run.summary.batch_id}.jsonl"
    write_jsonl(output_path, batch_run.records)

    return RedirectResponse(url="/api/v1/dev/quiz-console", status_code=303)


def _render_page(groups: list[_BatchGroup]) -> str:
    all_records = [record for group in groups for record in group.records]
    total = len(all_records)
    succeeded = sum(r.status == QuizBatchStatus.SUCCEEDED for r in all_records)
    failed = sum(r.status == QuizBatchStatus.FAILED for r in all_records)
    duplicates = sum(r.status == QuizBatchStatus.DUPLICATE for r in all_records)
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
<label>카테고리
<select name="topic">
<option value="랜덤">랜덤</option>
<option value="예·적금">예·적금</option>
<option value="채권">채권</option>
<option value="주식">주식</option>
<option value="펀드">펀드</option>
</select>
</label>
<label>생성 수
<input type="number" name="count" value="1" min="1" max="100">
</label>
<button type="submit">생성</button>
</form>
</section>
<h2>생성 기록</h2>
{_render_history(groups)}
<script>{_SCRIPT}</script>
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
    options = '<option value="랜덤">랜덤</option>'
    options += "".join(
        f'<option value="{question_type.value}">{question_type.value}</option>'
        for question_type in QuestionType
    )
    return options


def _render_filter_options(values: list[str], selected: str) -> str:
    all_selected = " selected" if not selected else ""
    options = f'<option value=""{all_selected}>전체</option>'
    options += "".join(
        f'<option value="{html.escape(value)}"'
        f"{' selected' if value == selected else ''}>"
        f"{html.escape(value)}</option>"
        for value in values
    )
    return options


def _render_history(groups: list[_BatchGroup]) -> str:
    if not groups:
        return '<p class="empty">아직 생성한 문제가 없습니다.</p>'

    return "".join(_render_batch_card(group) for group in groups)


def _render_batch_card(group: _BatchGroup) -> str:
    records = group.records
    total = len(records)
    succeeded = sum(r.status == QuizBatchStatus.SUCCEEDED for r in records)
    success_rate = round(succeeded / total * 100) if total else 0
    generated_at = datetime.fromtimestamp(group.mtime).strftime("%Y-%m-%d %H:%M")
    cost = _calculate_cost(records)
    duration = _format_duration(_total_elapsed_ms(records))
    batch_id = str(group.batch_id)

    tone = (
        "success"
        if success_rate == 100
        else ("danger" if succeeded == 0 else "warning")
    )
    summary = (
        "<summary>"
        f'<span class="cell">{html.escape(generated_at)}</span>'
        f'<span class="cell">{total}건 중 {succeeded}건 성공</span>'
        f'<span class="badge tone-{tone}">{success_rate}%</span>'
        f'<span class="cell">{html.escape(cost)}</span>'
        f'<span class="cell">{html.escape(duration)} 소요</span>'
        f'<span class="cell" style="color:#999;font-size:12px;">▾ 항목 보기</span>'
        "</summary>"
    )

    filter_toolbar = (
        '<div class="batch-filter">'
        "<label>유형 필터"
        f'<select id="qtype-{batch_id}" onchange="filterBatchItems(\'{batch_id}\')">'
        f"{_render_filter_options(_QUESTION_TYPES, '')}"
        "</select>"
        "</label>"
        "<label>카테고리 필터"
        f'<select id="topic-{batch_id}" onchange="filterBatchItems(\'{batch_id}\')">'
        f"{_render_filter_options(_CATEGORIES, '')}"
        "</select>"
        "</label>"
        "</div>"
    )

    items = "".join(_render_entry(group.mtime, record) for record in records)

    return (
        f'<details class="batch">{summary}<div class="batch-items">'
        f'{filter_toolbar}<div id="items-{batch_id}">{items}</div>'
        "</div></details>"
    )


def _calculate_cost(records: list[QuizBatchRecord]) -> str:
    total_usd = 0.0
    for record in records:
        if record.result is not None:
            ex = record.result.execution
            total_usd += ex.input_tokens * _INPUT_TOKEN_PRICE_USD
            total_usd += ex.output_tokens * _OUTPUT_TOKEN_PRICE_USD

    if total_usd == 0:
        return "비용 없음"

    return f"약 ${total_usd:.4f}"


def _total_elapsed_ms(records: list[QuizBatchRecord]) -> int:
    return sum(
        record.result.execution.elapsed_ms
        for record in records
        if record.result is not None
    )


def _format_duration(elapsed_ms: int) -> str:
    total_seconds = elapsed_ms // 1000

    if total_seconds < 60:
        return f"{total_seconds}초"

    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}분 {seconds}초"


def _render_entry(mtime: float, record: QuizBatchRecord) -> str:
    label, tone = _STATUS_LABELS[record.status]
    generated_at = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    topic = html.escape(record.input.topic)
    question_type = html.escape(record.input.question_type)

    if record.status == QuizBatchStatus.SUCCEEDED and record.result is not None:
        execution = record.result.execution
        tokens = f"입력 {execution.input_tokens} · 출력 {execution.output_tokens}"
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

    return (
        f'<details class="entry" data-question-type="{question_type}" '
        f'data-topic="{topic}">{summary}{_render_entry_detail(record)}</details>'
    )


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
