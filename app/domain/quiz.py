from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UsageType(StrEnum):
    SUB_CHAPTER = "SUB_CHAPTER"
    MAIN_CHAPTER = "MAIN_CHAPTER"
    DAILY_GENERAL = "DAILY_GENERAL"
    DAILY_NEWS = "DAILY_NEWS"


class QuestionType(StrEnum):
    TRUE_FALSE = "TRUE_FALSE"
    SINGLE_CHOICE = "SINGLE_CHOICE"
    SCENARIO = "SCENARIO"


class Difficulty(StrEnum):
    EASY = "EASY"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class QuizOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class QuizAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str = Field(min_length=1)


class QuizCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_key: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)


class ScenarioPersona(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    age: str = Field(min_length=1)
    job: str = Field(min_length=1)


class ScenarioRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assets: str = Field(min_length=1)
    risk: str = Field(min_length=1)
    goal: str = Field(min_length=1)


class ScenarioMarket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    reference_at: datetime
    bullets: list[str] = Field(min_length=1)


class QuizScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    persona: ScenarioPersona
    requirements: ScenarioRequirements
    market: ScenarioMarket
    constraints: list[str]
    paper_title: str = Field(min_length=1)


class Quiz(BaseModel):
    model_config = ConfigDict(extra="forbid")

    usage_type: UsageType
    question_type: QuestionType
    prompt: str = Field(min_length=1)
    scenario_json: QuizScenario | None
    options: list[QuizOption]
    correct_answer: QuizAnswer
    explanation: str = Field(min_length=1)
    difficulty: Difficulty
    citations: list[QuizCitation]


class QuizSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(ge=1)
    chunk_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    heading: str | None
    source_url: str | None
    published_at: datetime | None
    evidence_text: str = Field(min_length=1)


class QuizValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_valid: bool
    answer_valid: bool
    citation_valid: bool
    grounded: bool
    duplicate: bool
    errors: list[str]


class QuizExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)


class GroundingValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supported: bool
    reason: str = Field(min_length=1)
    unsupported_claims: list[str]


class QuizGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz: Quiz
    sources: list[QuizSource]
    validation: QuizValidation
    execution: QuizExecution


class QuizBatchStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"


class QuizBatchItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: str
    topic: str
    main_chapter_id: int | None = None
    sub_chapter_id: int | None = None
    usage_type: UsageType | None = None
    quest_date: date | None = None


class QuizBatchRequestItem(QuizBatchItemInput):
    count: int = Field(default=1, ge=1, strict=True)


class QuizBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[QuizBatchRequestItem] = Field(min_length=1)


class QuizBatchError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str = Field(min_length=1)
    errors: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    unsupported_claims: list[str]


class QuizBatchDuplicate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original_item_id: UUID
    prompt: str = Field(min_length=1)


class QuizBatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    item_id: UUID
    status: QuizBatchStatus
    input: QuizBatchItemInput
    result: QuizGenerationResult | None
    error: QuizBatchError | None
    duplicate: QuizBatchDuplicate | None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "QuizBatchRecord":
        if self.status == QuizBatchStatus.SUCCEEDED:
            valid = (
                self.result is not None
                and self.error is None
                and self.duplicate is None
            )
        elif self.status == QuizBatchStatus.FAILED:
            valid = (
                self.result is None
                and self.error is not None
                and self.duplicate is None
            )
        else:
            valid = (
                self.result is None
                and self.error is not None
                and self.duplicate is not None
            )

        if not valid:
            raise ValueError("배치 상태와 결과 필드 조합이 올바르지 않습니다.")

        return self


class QuizBatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    total: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    output_path: str | None = None


class ChapterType(StrEnum):
    FOUNDATION = "FOUNDATION"
    ASSET = "ASSET"


class SubChapterTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sub_chapter_id: int = Field(ge=1)
    main_chapter_id: int = Field(ge=1)
    title: str = Field(min_length=1)


class MainChapterTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_chapter_id: int = Field(ge=1)
    title: str = Field(min_length=1)
    chapter_type: ChapterType
    sub_chapters: list[SubChapterTarget]


class QuizGenerationTargets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_chapters: list[MainChapterTarget]


class BeBatchItemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: UUID
    result: str
    question_id: int | None = None
    status: str | None = None
    error_code: str | None = None
    error_message: str | None = None


class BeBatchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: UUID
    total: int = Field(ge=0)
    accepted: int = Field(ge=0)
    rejected: int = Field(ge=0)
    items: list[BeBatchItemResult]
