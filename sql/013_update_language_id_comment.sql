-- ============================================================
-- Atualização: Adicionar comentário ao campo language_id
-- ============================================================

-- Adiciona comentário explicativo ao campo language_id na tabela audio_presets
ALTER TABLE `audio_presets` 
MODIFY COLUMN `language_id` VARCHAR(10) NULL COMMENT 'Código ISO do idioma (ex: pt-BR, en-US, es-ES)';
