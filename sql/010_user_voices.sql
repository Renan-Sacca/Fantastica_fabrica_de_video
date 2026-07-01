-- ============================================================
-- Tabela: user_voices (Vozes Personalizadas por Usuário)
-- ============================================================

CREATE TABLE IF NOT EXISTS `user_voices` (
    `id`                INT             NOT NULL AUTO_INCREMENT,
    `voice_id`          VARCHAR(64)     NOT NULL,
    `user_id`           INT             NOT NULL,
    `name`              VARCHAR(255)    NOT NULL,
    `filename`          VARCHAR(255)    NOT NULL,
    `reference_text`    TEXT            NULL,
    `is_deleted`        TINYINT(1)      NOT NULL DEFAULT 0,
    `deleted_at`        DATETIME        NULL,
    `created_at`        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_user_voices_voice_id` (`voice_id`),
    INDEX `ix_user_voices_user_id` (`user_id`),
    INDEX `ix_user_voices_deleted` (`is_deleted`),
    CONSTRAINT `fk_user_voices_user` 
        FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) 
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
