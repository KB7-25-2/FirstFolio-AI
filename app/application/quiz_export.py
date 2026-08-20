from app.domain.quiz import QuizBatchRecord, QuizBatchStatus, UsageType


class QuizExportError(ValueError):
    pass


def to_be_quiz_payload(record: QuizBatchRecord) -> dict[str, object]:
    if record.status != QuizBatchStatus.SUCCEEDED or record.result is None:
        raise QuizExportError(
            f"성공하지 않은 레코드는 BE로 전송할 수 없습니다: item_id={record.item_id}"
        )

    quiz = record.result.quiz

    # DAILY_NEWS는 대·소단원에 속하지 않는 문항이라 main_chapter_id가 없는 게 정상이다.
    if quiz.usage_type != UsageType.DAILY_NEWS and record.input.main_chapter_id is None:
        raise QuizExportError(
            f"main_chapter_id가 없는 레코드는 BE로 전송할 수 없습니다: item_id={record.item_id}"
        )

    scenario_json = (
        quiz.scenario_json.model_dump(mode="json")
        if quiz.scenario_json is not None
        else None
    )

    return {
        "usage_type": quiz.usage_type.value,
        "main_chapter_id": record.input.main_chapter_id,
        "sub_chapter_id": record.input.sub_chapter_id,
        "question_type": quiz.question_type.value,
        "difficulty": quiz.difficulty.value,
        "prompt": quiz.prompt,
        "scenario_json": scenario_json,
        "options_json": [
            {"key": option.option_id, "label": option.text} for option in quiz.options
        ],
        "correct_answer_json": {"key": quiz.correct_answer.option_id},
        "explanation": quiz.explanation,
        "source_refs_json": None,
        "quest_date": (
            record.input.quest_date.isoformat()
            if record.input.quest_date is not None
            else None
        ),
    }
