from pathlib import Path

import pytest

from app.infrastructure.document_loaders.text import (
    EmptyDocumentError,
    TextDocumentLoader,
    UnsupportedDocumentFormatError,
)


def test_load_text_document(tmp_path: Path) -> None:
    file_path = tmp_path / "deposit_guide.txt"
    original_content = "예금의 기본 개념\n\n예금은 금융기관에 돈을 맡기는 상품이다.\n"
    file_path.write_text(original_content, encoding="utf-8")

    document = TextDocumentLoader().load(file_path)

    assert document.title == "deposit_guide"
    assert document.content == original_content
    assert document.source == str(file_path)


def test_load_missing_document(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match="문서 파일을 찾을 수 없습니다"):
        TextDocumentLoader().load(missing_path)


def test_load_directory_path(tmp_path: Path) -> None:
    with pytest.raises(
        IsADirectoryError,
        match="문서 경로가 파일이 아닙니다",
    ):
        TextDocumentLoader().load(tmp_path)


def test_load_unsupported_document_format(tmp_path: Path) -> None:
    file_path = tmp_path / "report.pdf"
    file_path.write_text("금융 보고서", encoding="utf-8")

    with pytest.raises(
        UnsupportedDocumentFormatError,
        match="지원하지 않는 문서 형식입니다",
    ):
        TextDocumentLoader().load(file_path)


def test_load_empty_document(tmp_path: Path) -> None:
    file_path = tmp_path / "empty.txt"
    file_path.write_text("  \n\t", encoding="utf-8")

    with pytest.raises(
        EmptyDocumentError,
        match="문서에 내용이 없습니다",
    ):
        TextDocumentLoader().load(file_path)
