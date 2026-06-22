-- ============================================================
-- Tabela: permissions (permissões por usuário)
-- ============================================================
-- Cada linha representa uma permissão concedida a um usuário.
-- Permissões disponíveis:
--   whatsapp_videos  → pode criar/ver vídeos de WhatsApp
--   whatsapp_extract → pode usar a extração de conversas
-- ============================================================

CREATE TABLE IF NOT EXISTS `permissions` (
    `id`         INT          NOT NULL AUTO_INCREMENT,
    `user_id`    INT          NOT NULL,
    `permission` VARCHAR(64)  NOT NULL,
    `granted_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_permissions_user_permission` (`user_id`, `permission`),
    CONSTRAINT `fk_permissions_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
