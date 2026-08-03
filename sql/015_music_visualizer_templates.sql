-- Templates de configurações reutilizáveis do Music Visualizer.
CREATE TABLE IF NOT EXISTS `music_visualizer_templates` (
    `id`            INT AUTO_INCREMENT PRIMARY KEY,
    `template_id`   VARCHAR(64)  NOT NULL UNIQUE,
    `user_id`       INT          NOT NULL,
    `name`          VARCHAR(255) NOT NULL,
    `description`   TEXT         NULL,
    `template_data` LONGTEXT     NOT NULL COMMENT 'JSON das configurações, sem arquivos',
    `is_deleted`    TINYINT(1)   NOT NULL DEFAULT 0,
    `deleted_at`    DATETIME     NULL,
    `created_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `ix_mv_templates_user_id` (`user_id`),
    INDEX `ix_mv_templates_deleted` (`is_deleted`),
    CONSTRAINT `fk_mv_templates_user`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
