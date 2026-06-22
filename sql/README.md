# SQL Scripts — Fantástica Fábrica de Vídeo

Scripts de criação de todas as tabelas do banco MySQL `fabrica_video_db`.

## Tabelas

| # | Arquivo | Tabela | Descrição |
|---|---------|--------|-----------|
| 1 | `001_jobs.sql` | `jobs` | Tabela base com campos comuns a todos os tipos de vídeo |
| 2 | `002_whatsapp_jobs.sql` | `whatsapp_jobs` | Config específica de vídeos WhatsApp (herda de jobs) |
| 3 | `003_whatsapp_extract_jobs.sql` | `whatsapp_extract_jobs` | Extração de conversas de vídeo (herda de jobs) |
| 4 | `004_text_correction_jobs.sql` | `text_correction_jobs` | Correção de texto via IA — tabela independente |

## Como usar

### Executar um script individual
```bash
mysql -u user_pessoal -p fabrica_video_db < sql/004_text_correction_jobs.sql
```

### Executar todos (via SQLAlchemy/Python)
Os serviços (web, worker, agente) já criam as tabelas automaticamente via `init_db()` ao iniciar. Estes scripts servem como **documentação** e **backup** caso precise recriar o banco manualmente.

## Notas
- As tabelas `whatsapp_jobs` e `whatsapp_extract_jobs` usam **joined-table inheritance** (FK para `jobs.id`)
- A tabela `text_correction_jobs` é **independente** — não herda de `jobs`
- Todas usam `ENGINE=InnoDB` com charset `utf8mb4`
