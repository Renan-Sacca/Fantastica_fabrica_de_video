-- ============================================================
-- Adicionar plano de vozes à tabela users
-- ============================================================

ALTER TABLE `users` 
ADD COLUMN `voice_plan_id` INT NULL AFTER `is_admin`,
ADD CONSTRAINT `fk_users_voice_plan` 
    FOREIGN KEY (`voice_plan_id`) 
    REFERENCES `voice_plans` (`id`) 
    ON DELETE SET NULL;

-- Atualizar usuários existentes
-- Admin recebe plano ilimitado, outros recebem plano básico
UPDATE `users` 
SET `voice_plan_id` = (
    SELECT `id` FROM `voice_plans` 
    WHERE `is_unlimited` = 1 
    LIMIT 1
)
WHERE `is_admin` = 1;

UPDATE `users` 
SET `voice_plan_id` = (
    SELECT `id` FROM `voice_plans` 
    WHERE `is_unlimited` = 0 
    LIMIT 1
)
WHERE `is_admin` = 0 AND `voice_plan_id` IS NULL;
