# SQL Scripts — Fantástica Fábrica de Vídeo

Scripts de criação de todas as tabelas do banco MySQL `fabrica_video_db`.

## Tabelas

| # | Arquivo | Tabela | Descrição |
|---|---------|--------|-----------|
| 1 | `001_jobs.sql` | `jobs` | Tabela base com campos comuns a todos os tipos de vídeo (inclui `user_id`) |
| 2 | `002_whatsapp_jobs.sql` | `whatsapp_jobs` | Config específica de vídeos WhatsApp (herda de jobs) |
| 3 | `003_whatsapp_extract_jobs.sql` | `whatsapp_extract_jobs` | Extração de conversas de vídeo (herda de jobs) |
| 4 | `004_text_correction_jobs.sql` | `text_correction_jobs` | Correção de texto via IA — tabela independente (inclui `user_id`) |
| 5 | `005_users.sql` | `users` | Usuários — autenticação por email/senha |
| 6 | `006_permissions.sql` | `permissions` | Permissões por usuário (whatsapp_videos, whatsapp_extract) |
| 7 | `007_add_user_id_to_jobs.sql` | — | **Migração apenas** — adiciona `user_id` em bancos existentes |

## Como usar

### Banco novo (do zero)
```bash
mysql -u user_pessoal -p < sql/000_all.sql
```

### Executar um script individual
```bash
mysql -u user_pessoal -p fabrica_video_db < sql/005_users.sql
```

### Migração de banco existente (adicionar user_id)
Se você já tinha o banco criado antes da versão com usuários, execute:
```bash
mysql -u user_pessoal -p fabrica_video_db < sql/007_add_user_id_to_jobs.sql
mysql -u user_pessoal -p fabrica_video_db < sql/005_users.sql
mysql -u user_pessoal -p fabrica_video_db < sql/006_permissions.sql
```

### Executar todos (via SQLAlchemy/Python)
Os serviços (web, worker, agente) já criam as tabelas automaticamente via `init_db()` ao iniciar. Estes scripts servem como **documentação** e **backup** caso precise recriar o banco manualmente.

## Sistema de Permissões

| Permissão | Descrição |
|-----------|-----------|
| `whatsapp_videos` | Pode criar e visualizar vídeos de WhatsApp |
| `whatsapp_extract` | Pode usar a extração de conversas por vídeo |
| `use_ai` | Pode usar a correção de texto via IA (Gemini) |

Permissões são gerenciadas em `/auth/admin/users` (acessível a qualquer usuário logado).

## Notas
- As tabelas `whatsapp_jobs` e `whatsapp_extract_jobs` usam **joined-table inheritance** (FK para `jobs.id`)
- A tabela `text_correction_jobs` é **independente** — não herda de `jobs`
- Todas usam `ENGINE=InnoDB` com charset `utf8mb4`
- A correção via IA sempre usa **Gemini** com nova conversa (modo anônimo — sem salvar no histórico)
