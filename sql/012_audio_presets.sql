-- ============================================================
-- Tabela: audio_presets (Configurações Salvas de Parâmetros de Áudio)
-- ============================================================

CREATE TABLE IF NOT EXISTS `audio_presets` (
    `id`                    INT             NOT NULL AUTO_INCREMENT,
    `preset_id`             VARCHAR(64)     NOT NULL,
    `user_id`               INT             NOT NULL,
    `name`                  VARCHAR(255)    NOT NULL,
    `description`           TEXT            NULL,
    
    -- Parâmetros de geração
    `num_step`              INT             NULL,
    `guidance_scale`        FLOAT           NULL,
    `t_shift`               FLOAT           NULL,
    `position_temperature`  FLOAT           NULL,
    `class_temperature`     FLOAT           NULL,
    `layer_penalty_factor`  FLOAT           NULL,
    `speed`                 FLOAT           NULL,
    `duration`              FLOAT           NULL,
    `audio_chunk_duration`  FLOAT           NULL,
    `audio_chunk_threshold` FLOAT           NULL,
    `language_id`           VARCHAR(10)     NULL,
    `denoise`               TINYINT(1)      NULL,
    `preprocess_prompt`     TINYINT(1)      NULL,
    `postprocess_output`    TINYINT(1)      NULL,
    
    -- Controle
    `is_deleted`            TINYINT(1)      NOT NULL DEFAULT 0,
    `deleted_at`            DATETIME        NULL,
    `created_at`            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`            DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_audio_presets_preset_id` (`preset_id`),
    INDEX `ix_audio_presets_user_id` (`user_id`),
    INDEX `ix_audio_presets_deleted` (`is_deleted`),
    CONSTRAINT `fk_audio_presets_user` 
        FOREIGN KEY (`user_id`) 
        REFERENCES `users` (`id`) 
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
