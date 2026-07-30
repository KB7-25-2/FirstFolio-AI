import pytest

from app.infrastructure.tokenizers.kiwi import KiwiTokenizer


@pytest.fixture(scope="module")
def tokenizer() -> KiwiTokenizer:
    return KiwiTokenizer()


def test_tokenize_korean_financial_sentence(
    tokenizer: KiwiTokenizer,
) -> None:
    tokens = tokenizer.tokenize(
        "예금은 금융기관에 돈을 맡기는 상품이다. 금리는 연 3.5%다."
    )

    assert {
        "예금",
        "금융",
        "기관",
        "돈",
        "맡기",
        "상품",
        "금리",
        "3.5",
    }.issubset(tokens)

    assert "은" not in tokens
    assert "이" not in tokens
    assert "." not in tokens


def test_normalize_english_tokens_to_lowercase(
    tokenizer: KiwiTokenizer,
) -> None:
    tokens = tokenizer.tokenize("ETF 상품은 3.5%의 수익을 냈다.")

    assert "etf" in tokens
    assert "ETF" not in tokens
    assert "3.5" in tokens


def test_tokenize_empty_text(
    tokenizer: KiwiTokenizer,
) -> None:
    assert tokenizer.tokenize("  \n\t") == []
