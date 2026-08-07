from unittest.mock import Mock, patch

from app.application.quiz_validation import normalize_quiz_prompt
from app.core.config import Settings
from app.infrastructure.repositories.mysql_quiz_prompt import (
    MySQLQuizPromptRepository,
)


def _settings() -> Settings:
    return Settings(
        mysql_password="test-password",
        _env_file=None,
    )


def _connection_and_cursor() -> tuple[Mock, Mock]:
    cursor = Mock()
    connection = Mock()
    connection.cursor.return_value = cursor
    return connection, cursor


@patch("app.infrastructure.repositories.mysql_quiz_prompt.create_mysql_connection")
def test_find_all_prompts_returns_stored_prompts(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    cursor.fetchall.return_value = [("예금은 무엇인가?",), ("채권이란?",)]
    repository = MySQLQuizPromptRepository(_settings())

    prompts = repository.find_all_prompts()

    assert prompts == ["예금은 무엇인가?", "채권이란?"]
    cursor.execute.assert_called_once_with("SELECT prompt FROM AI_QUIZ_PROMPTS")
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_quiz_prompt.create_mysql_connection")
def test_save_inserts_prompt_with_normalized_hash(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLQuizPromptRepository(_settings())

    repository.save(
        prompt="예금은 무엇인가?",
        question_type="SINGLE_CHOICE",
        topic="예·적금",
    )

    sql, parameters = cursor.execute.call_args.args
    normalized_sql = " ".join(sql.split())
    prompt_hash, prompt, question_type, topic = parameters

    assert "INSERT IGNORE INTO AI_QUIZ_PROMPTS" in normalized_sql
    assert prompt == "예금은 무엇인가?"
    assert question_type == "SINGLE_CHOICE"
    assert topic == "예·적금"
    assert len(prompt_hash) == 64
    connection.commit.assert_called_once_with()
    connection.rollback.assert_not_called()
    cursor.close.assert_called_once_with()
    connection.close.assert_called_once_with()


@patch("app.infrastructure.repositories.mysql_quiz_prompt.create_mysql_connection")
def test_save_produces_same_hash_for_normalized_duplicate_prompts(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    repository = MySQLQuizPromptRepository(_settings())

    repository.save(
        prompt="예금은 무엇인가?", question_type="SINGLE_CHOICE", topic="예·적금"
    )
    first_hash = cursor.execute.call_args.args[1][0]

    repository.save(
        prompt="  예금은...\n무엇인가!  ",
        question_type="SINGLE_CHOICE",
        topic="예·적금",
    )
    second_hash = cursor.execute.call_args.args[1][0]

    assert first_hash == second_hash
    assert normalize_quiz_prompt("예금은 무엇인가?") == normalize_quiz_prompt(
        "  예금은...\n무엇인가!  "
    )


@patch("app.infrastructure.repositories.mysql_quiz_prompt.create_mysql_connection")
def test_save_rolls_back_on_error(
    create_connection_mock: Mock,
) -> None:
    connection, cursor = _connection_and_cursor()
    create_connection_mock.return_value = connection
    cursor.execute.side_effect = RuntimeError("연결 오류")
    repository = MySQLQuizPromptRepository(_settings())

    try:
        repository.save(
            prompt="예금은 무엇인가?", question_type="SINGLE_CHOICE", topic="예·적금"
        )
    except RuntimeError:
        pass

    connection.rollback.assert_called_once_with()
    connection.commit.assert_not_called()
    connection.close.assert_called_once_with()
