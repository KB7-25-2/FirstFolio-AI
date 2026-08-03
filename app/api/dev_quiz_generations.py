from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from app.application.quiz_generation import (
    QuizGenerationService,
    QuizGenerationValidationError,
)
from app.domain.quiz import QuestionType, QuizGenerationResult
from app.quiz_mvp import create_quiz_generation_service

router = APIRouter(
    prefix="/api/v1/dev",
    tags=["development"],
)


class QuizGenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: QuestionType
    topic: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1),
    ]


def get_quiz_generation_service(
    request: Request,
) -> QuizGenerationService:
    return create_quiz_generation_service(request.app.state.settings)


@router.post(
    "/quiz-generations",
    response_model=QuizGenerationResult,
    status_code=status.HTTP_200_OK,
)
def create_quiz_generation(
    payload: QuizGenerationRequest,
    service: Annotated[
        QuizGenerationService,
        Depends(get_quiz_generation_service),
    ],
) -> QuizGenerationResult | JSONResponse:
    try:
        return service.generate(
            question_type=payload.question_type,
            topic=payload.topic,
        )
    except QuizGenerationValidationError as error:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if error.stage == "search"
            else status.HTTP_422_UNPROCESSABLE_CONTENT
        )
        return JSONResponse(
            status_code=status_code,
            content={
                "stage": error.stage,
                "errors": list(error.errors),
                "reason": error.reason,
                "unsupported_claims": list(error.unsupported_claims),
            },
        )
