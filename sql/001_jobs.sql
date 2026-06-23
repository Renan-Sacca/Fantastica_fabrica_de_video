-- ============================================================
-- Tabela: jobs (base para todos os tipos de vídeo)
-- ============================================================
-- Usa herança por junção (joined-table inheritance) do SQLAlchemy.
-- O campo `video_type` discrimina o tipo de job.
-- ============================================================

CREATE TABLE IF NOT EXISTS `jobs` (
    `id`               INT             NOT NULL AUTO_INCREMENT,
    `job_id`           VARCHAR(64)     NOT NULL,
    `title`            VARCHAR(255)    NOT NULL,
    `video_type`       VARCHAR(50)     NOT NULL,

    -- Usuário dono do job
    `user_id`          INT             NULL,

    -- Estado do processamento (atualizado pelo worker)
    `status`           VARCHAR(30)     NOT NULL DEFAULT 'pending',
    `is_deleted`       TINYINT(1)      NOT NULL DEFAULT 0,
    `deleted_at`       DATETIME        NULL,
    `progress`         FLOAT           NOT NULL DEFAULT 0.0,
    `detail`           TEXT            NULL,
    `error`            TEXT            NULL,

    -- Referências do Google Drive
    `drive_folder_id`  VARCHAR(128)    NULL,
    `metadata_file_id` VARCHAR(128)    NULL,
    `video_drive_id`   VARCHAR(128)    NULL,
    `video_url`        VARCHAR(512)    NULL,

    -- Timestamps
    `created_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_jobs_job_id` (`job_id`),
    INDEX `ix_jobs_job_id` (`job_id`),
    INDEX `ix_jobs_video_type` (`video_type`),
    INDEX `ix_jobs_user_id` (`user_id`),
    INDEX `ix_jobs_is_deleted` (`is_deleted`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
