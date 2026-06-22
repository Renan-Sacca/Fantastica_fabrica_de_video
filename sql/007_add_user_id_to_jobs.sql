-- ============================================================
-- Migração: Adiciona user_id à tabela jobs e text_correction_jobs
-- ============================================================
-- Execute APENAS se o banco já existia antes desta versão.
-- Se criou o banco do zero com 000_all.sql, NÃO execute este script.
-- ============================================================

-- Adicionar user_id em jobs (se não existir)
ALTER TABLE `jobs`
    ADD COLUMN IF NOT EXISTS `user_id` INT NULL AFTER `video_type`;

-- Adicionar FK (ignorar se já existir — MySQL não tem IF NOT EXISTS para FK)
-- Se rodar em banco novo, o 000_all.sql já inclui as colunas.

-- Adicionar user_id em text_correction_jobs (se não existir)
ALTER TABLE `text_correction_jobs`
    ADD COLUMN IF NOT EXISTS `user_id` INT NULL AFTER `provider`;
