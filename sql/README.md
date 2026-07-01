# Scripts SQL

Scripts SQL para criar e atualizar o banco de dados do sistema.

## Ordem de Execução

Execute os scripts na ordem numérica:

1. `000_all.sql` - Script completo (alternativa ao processo incremental)
2. `001_jobs.sql` - Tabela de jobs de vídeo
3. `002_whatsapp_jobs.sql` - Tabela de jobs de WhatsApp
4. `003_whatsapp_extract_jobs.sql` - Tabela de extração de WhatsApp
5. `004_text_correction_jobs.sql` - Tabela de correção de texto
6. `005_users.sql` - Tabela de usuários
7. `006_permissions.sql` - Tabela de permissões
8. `007_add_user_id_to_jobs.sql` - Adiciona user_id às tabelas de jobs
9. `008_add_fk_user_references.sql` - Adiciona foreign keys para users
10. `009_voice_plans.sql` - **NOVO** - Tabela de planos de vozes
11. `010_user_voices.sql` - **NOVO** - Tabela de vozes personalizadas por usuário
12. `011_add_voice_plan_to_users.sql` - **NOVO** - Adiciona plano de vozes aos usuários

## Novos Scripts (Sistema de Vozes)

### 009_voice_plans.sql
Cria a tabela `voice_plans` com os planos de vozes:
- Plano Básico: até 10 vozes personalizadas
- Plano Admin: vozes ilimitadas

### 010_user_voices.sql
Cria a tabela `user_voices` para armazenar vozes personalizadas por usuário:
- Vinculada ao usuário (com FK)
- Armazena nome, arquivo e texto de referência
- Soft delete (is_deleted)

### 011_add_voice_plan_to_users.sql
Adiciona campo `voice_plan_id` à tabela `users`:
- Admins recebem automaticamente o plano ilimitado
- Usuários comuns recebem o plano básico

## Como Aplicar

### Método 1: Via MySQL Client
```bash
mysql -u usuario -p nome_banco < sql/009_voice_plans.sql
mysql -u usuario -p nome_banco < sql/010_user_voices.sql
mysql -u usuario -p nome_banco < sql/011_add_voice_plan_to_users.sql
```

### Método 2: Via Docker
```bash
docker exec -i container_mysql mysql -u root -p nome_banco < sql/009_voice_plans.sql
docker exec -i container_mysql mysql -u root -p nome_banco < sql/010_user_voices.sql
docker exec -i container_mysql mysql -u root -p nome_banco < sql/011_add_voice_plan_to_users.sql
```

## Migração de Vozes Existentes

Se você tem vozes no formato antigo (arquivo JSON `_custom_voices.json`), será necessário:

1. Executar os scripts SQL acima
2. Criar um script Python para migrar as vozes do JSON para o banco de dados
3. Associar cada voz a um usuário

Exemplo de script de migração:
```python
import json
from pathlib import Path
from app.repositories import user_voices

# Ler arquivo JSON antigo
json_path = Path("/caminho/para/_custom_voices.json")
if json_path.exists():
    voices = json.load(json_path.open())
    
    # Para cada voz, criar entrada no banco
    for voice_id, info in voices.items():
        user_voices.create_voice(
            voice_id=voice_id,
            user_id=1,  # Definir usuário apropriado
            name=info["name"],
            filename=info["filename"],
            reference_text=info.get("reference_text", "")
        )
```
