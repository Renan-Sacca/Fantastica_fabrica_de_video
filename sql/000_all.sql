-- ============================================================
-- Fantástica Fábrica de Vídeo — Scripts de Criação de Tabelas
-- ============================================================
-- Database: fabrica_video_db
-- Charset: utf8mb4
--
-- Ordem de execução:
--   1. 001_jobs.sql                   (tabela base)
--   2. 002_whatsapp_jobs.sql          (herança de jobs)
--   3. 003_whatsapp_extract_jobs.sql  (herança de jobs)
--   4. 004_text_correction_jobs.sql   (tabela independente)
--   5. 005_users.sql                  (usuários)
--   6. 006_permissions.sql            (permissões por usuário)
--   7. 007_add_user_id_to_jobs.sql    (FK de user nos jobs)
--
-- Para executar todos de uma vez:
--   mysql -u user -p fabrica_video_db < sql/000_all.sql
-- ============================================================

-- Criar database se não existir
CREATE DATABASE IF NOT EXISTS `fabrica_video_db`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE `fabrica_video_db`;

-- ── 1. Tabela base: jobs ──
SOURCE sql/001_jobs.sql;

-- ── 2. Tabela: whatsapp_jobs ──
SOURCE sql/002_whatsapp_jobs.sql;

-- ── 3. Tabela: whatsapp_extract_jobs ──
SOURCE sql/003_whatsapp_extract_jobs.sql;

-- ── 4. Tabela: text_correction_jobs ──
SOURCE sql/004_text_correction_jobs.sql;

-- ── 5. Tabela: users ──
SOURCE sql/005_users.sql;

-- ── 6. Tabela: permissions ──
SOURCE sql/006_permissions.sql;

-- ── 7. FKs de user_id nos jobs ──
SOURCE sql/008_add_fk_user_references.sql;

-- Para migração de banco existente:
-- SOURCE sql/007_add_user_id_to_jobs.sql;
