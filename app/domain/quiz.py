from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UsageType(StrEnum):
    SUB_CHAPTER = "SUB_CHAPTER"
    MAIN_CHAPTER = "MAIN_CHAPTER"


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


class QuizScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character: str = Field(min_length=1)
    financial_context: str = Field(min_length=1)
    constraints: list[str]


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
