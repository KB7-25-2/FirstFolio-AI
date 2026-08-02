CREATE DATABASE IF NOT EXISTS `firstfolio_ai`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE `firstfolio_ai`;

CREATE TABLE IF NOT EXISTS `AI_DOCUMENTS` (
    `document_id` BIGINT NOT NULL AUTO_INCREMENT,
    `document_type` VARCHAR(30) NOT NULL,
    `category` VARCHAR(50) NULL,
    `title` VARCHAR(300) NOT NULL,
    `original_filename` VARCHAR(255) NOT NULL,
    `content_type` VARCHAR(100) NOT NULL,
    `s3_object_key` VARCHAR(1000) NOT NULL,
    `s3_version_id` VARCHAR(255) NOT NULL,
    `source_url` VARCHAR(1000) NULL,
    `publisher` VARCHAR(150) NULL,
    `published_at` DATETIME NULL,
    `status` VARCHAR(30) NOT NULL,
    `error_message` TEXT NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`document_id`)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `AI_DOCUMENT_CHUNKS` (
    `chunk_id` BIGINT NOT NULL AUTO_INCREMENT,
    `document_id` BIGINT NOT NULL,
    `chunk_key` VARCHAR(150) NOT NULL,
    `chunk_order` INT NOT NULL,
    `chunk_type` VARCHAR(30) NOT NULL,
    `heading` VARCHAR(500) NULL,
    `content` LONGTEXT NOT NULL,
    `metadata_json` JSON NULL,
    `token_count` INT NULL,
    `indexed_at` DATETIME NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`chunk_id`),
    CONSTRAINT `uq_ai_document_chunks_chunk_key`
        UNIQUE (`chunk_key`),
    CONSTRAINT `uq_ai_document_chunks_document_order`
        UNIQUE (`document_id`, `chunk_order`),
    CONSTRAINT `fk_ai_document_chunks_document`
        FOREIGN KEY (`document_id`)
        REFERENCES `AI_DOCUMENTS` (`document_id`)
        ON DELETE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARACTER SET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;
