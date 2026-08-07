from typing import Protocol


class QuizPromptRepository(Protocol):
    # 배치 시작 전 중복 판별에 사용할 기존 성공 질문 전체 조회
    def find_all_prompts(self) -> list[str]: ...

    # 생성 성공한 질문을 다음 배치의 중복 판별을 위해 저장
    def save(
        self,
        *,
        prompt: str,
        question_type: str,
        topic: str,
    ) -> None: ...
