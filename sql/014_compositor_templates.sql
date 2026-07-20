-- Migration: compositor_templates
-- Tabela para salvar templates/estruturas reutilizáveis do Vídeo Compositor.
-- O campo template_data armazena JSON com toda a configuração do vídeo.

CREATE TABLE IF NOT EXISTS compositor_templates (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    template_id     VARCHAR(64)   NOT NULL UNIQUE,
    user_id         INT           NOT NULL,
    name            VARCHAR(255)  NOT NULL,
    description     TEXT          NULL,
    template_data   LONGTEXT      NOT NULL COMMENT 'JSON com a estrutura do template',
    is_deleted      TINYINT(1)    NOT NULL DEFAULT 0,
    deleted_at      DATETIME      NULL,
    created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_template_id (template_id),
    INDEX idx_user_id (user_id),
    INDEX idx_is_deleted (is_deleted),

    CONSTRAINT fk_compositor_templates_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
