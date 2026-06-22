-- ============================================================
-- Tabela: whatsapp_extract_jobs (herda de jobs)
-- ============================================================
-- Dados de extração de conversas a partir de vídeos.
-- Mantém cache do texto extraído para evitar leituras no Drive.
-- ============================================================

CREATE TABLE IF NOT EXISTS `whatsapp_extract_jobs` (
    `id`                INT             NOT NULL,

    -- IDs dos arquivos no Google Drive
    `video_original_id` VARCHAR(128)   NULL,
    `conversa_txt_id`   VARCHAR(128)   NULL,
    `conversa_json_id`  VARCHAR(128)   NULL,

    -- Cache do texto extraído (evita ler do Drive toda vez)
    `conversa_text`     MEDIUMTEXT     NULL,

    PRIMARY KEY (`id`),
    CONSTRAINT `fk_whatsapp_extract_jobs_id`
        FOREIGN KEY (`id`) REFERENCES `jobs` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
