from typing import Protocol

from app.domain.quiz import QuizGenerationTargets


class QuizTargetRepository(Protocol):
    # Spring에서 현재 서비스 대상인 전체 활성 대·소단원 조회
    def find_targets(self) -> QuizGenerationTargets: ...
