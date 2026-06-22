-- ============================================================
-- Tabela: whatsapp_jobs (herda de jobs)
-- ============================================================
-- Configurações específicas para vídeos de conversa de WhatsApp.
-- Usa joined-table inheritance: FK para jobs.id.
-- ============================================================

CREATE TABLE IF NOT EXISTS `whatsapp_jobs` (
    `id`               INT             NOT NULL,

    -- Configurações do vídeo WhatsApp
    `contact_name`     VARCHAR(255)    NULL,
    `contact_status`   VARCHAR(255)    NULL,
    `video_format`     VARCHAR(30)     NULL,
    `fps`              INT             NULL,
    `speed`            FLOAT           NULL,
    `reading_speed`    FLOAT           NULL,
    `scroll_speed`     FLOAT           NULL,
    `animation_style`  VARCHAR(50)     NULL,

    PRIMARY KEY (`id`),
    CONSTRAINT `fk_whatsapp_jobs_id`
        FOREIGN KEY (`id`) REFERENCES `jobs` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
