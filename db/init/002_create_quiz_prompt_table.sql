USE `firstfolio_ai`;

CREATE TABLE IF NOT EXISTS `AI_QUIZ_PROMPTS` (
    `id` BIGINT NOT NULL AUTO_INCREMENT,
    `prompt_hash` CHAR(64) NOT NULL,
    `prompt` TEXT NOT NULL,
    `question_type` VARCHAR(30) NOT NULL,
    `topic` VARCHAR(100) NOT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    CONSTRAINT `uq_ai_quiz_prompts_prompt_hash`
        UNIQUE (`prompt_hash`)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
