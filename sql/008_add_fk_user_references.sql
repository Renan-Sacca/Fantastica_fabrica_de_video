-- ============================================================
-- Adiciona as FK de user_id depois que a tabela users existe
-- ============================================================
-- Execute após 005_users.sql e 006_permissions.sql.
-- O 000_all.sql já inclui este passo na ordem correta.
-- ============================================================

ALTER TABLE `jobs`
    ADD CONSTRAINT `fk_jobs_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE SET NULL;

ALTER TABLE `text_correction_jobs`
    ADD CONSTRAINT `fk_text_correction_jobs_user_id`
        FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
        ON DELETE SET NULL;
