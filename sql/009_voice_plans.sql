-- ============================================================
-- Tabela: voice_plans (Planos de Vozes)
-- ============================================================

CREATE TABLE IF NOT EXISTS `voice_plans` (
    `id`                INT             NOT NULL AUTO_INCREMENT,
    `name`              VARCHAR(100)    NOT NULL,
    `description`       TEXT            NULL,
    `max_voices`        INT             NOT NULL DEFAULT 10,
    `is_unlimited`      TINYINT(1)      NOT NULL DEFAULT 0,
    `is_active`         TINYINT(1)      NOT NULL DEFAULT 1,
    `created_at`        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_voice_plans_name` (`name`),
    INDEX `ix_voice_plans_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Inserir planos padrão
INSERT INTO `voice_plans` (`name`, `description`, `max_voices`, `is_unlimited`, `is_active`) 
VALUES 
    ('Plano Básico', 'Plano inicial com até 10 vozes personalizadas', 10, 0, 1),
    ('Plano Admin', 'Plano administrativo com vozes ilimitadas', 0, 1, 1)
ON DUPLICATE KEY UPDATE `description` = VALUES(`description`);
