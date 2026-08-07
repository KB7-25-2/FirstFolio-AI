import hashlib

from app.application.quiz_validation import normalize_quiz_prompt
from app.core.config import Settings
from app.infrastructure.database import create_mysql_connection


class MySQLQuizPromptRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def find_all_prompts(self) -> list[str]:
        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.execute("SELECT prompt FROM AI_QUIZ_PROMPTS")
                rows = cursor.fetchall()
            finally:
                cursor.close()
        finally:
            connection.close()

        return [str(row[0]) for row in rows]

    def save(
        self,
        *,
        prompt: str,
        question_type: str,
        topic: str,
    ) -> None:
        prompt_hash = self._hash_prompt(prompt)
        connection = create_mysql_connection(self._settings)

        try:
            cursor = connection.cursor()

            try:
                cursor.execute(
                    """
                    INSERT IGNORE INTO AI_QUIZ_PROMPTS (
                        prompt_hash,
                        prompt,
                        question_type,
                        topic
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (prompt_hash, prompt, question_type, topic),
                )
                connection.commit()
            finally:
                cursor.close()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _hash_prompt(prompt: str) -> str:
        normalized = normalize_quiz_prompt(prompt)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
