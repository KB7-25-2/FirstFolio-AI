from langchain_openai import ChatOpenAI

_PROMPT_TEMPLATE = (
    "다음은 금융 뉴스 기사의 제목과 원문 발췌입니다. "
    "핵심 내용만 담아 2~3문장의 자연스러운 한국어 요약을 작성하세요. "
    "원문에 없는 숫자·금액·금리·날짜를 추가하거나 추측하지 마세요.\n\n"
    "제목: {title}\n원문 발췌: {description}"
)


class OpenAINewsSummarizer:
    def __init__(
        self,
        model: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._client = ChatOpenAI(
            model=model,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )

    def summarize(self, title: str, description: str) -> str:
        prompt = _PROMPT_TEMPLATE.format(title=title, description=description)
        response = self._client.invoke(prompt)
        return str(response.content).strip()
