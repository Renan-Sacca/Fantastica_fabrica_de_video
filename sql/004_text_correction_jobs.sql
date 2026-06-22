-- ============================================================
-- Tabela: text_correction_jobs (independente — NÃO herda de jobs)
-- ============================================================
-- Jobs de correção de texto via IA (ChatGPT/Gemini).
-- Compartilhada entre:
--   - web (cria o job e consulta resultado)
--   - agente (processa e salva o texto corrigido)
-- ============================================================

CREATE TABLE IF NOT EXISTS `text_correction_jobs` (
    `id`               INT             NOT NULL AUTO_INCREMENT,
    `job_id`           VARCHAR(64)     NOT NULL,

    -- Estado
    `status`           VARCHAR(30)     NOT NULL DEFAULT 'pending',
    `provider`         VARCHAR(30)     NOT NULL DEFAULT 'chatgpt',

    -- Texto
    `raw_text`         MEDIUMTEXT      NULL COMMENT 'Texto bruto recebido (transcrição OCR)',
    `corrected_text`   MEDIUMTEXT      NULL COMMENT 'Texto corrigido pela IA',
    `error`            TEXT            NULL COMMENT 'Mensagem de erro (se houver)',

    -- Timestamps
    `created_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_text_correction_job_id` (`job_id`),
    INDEX `ix_text_correction_job_id` (`job_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
