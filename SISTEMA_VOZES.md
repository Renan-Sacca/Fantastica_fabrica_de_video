# 🎤 Sistema de Vozes Personalizadas

## 📋 Visão Geral

O sistema de vozes foi **completamente reformulado** para trabalhar com banco de dados MySQL ao invés de arquivo JSON. Agora cada usuário possui suas próprias vozes personalizadas, com limites baseados em planos.

## 🆕 O Que Mudou

### Antes (Sistema Antigo)
- ❌ Vozes armazenadas em arquivo JSON (`_custom_voices.json`)
- ❌ Vozes globais (compartilhadas entre todos os usuários)
- ❌ Sem limite de vozes
- ❌ Sem controle de propriedade

### Agora (Sistema Novo)
- ✅ Vozes armazenadas no MySQL (tabela `user_voices`)
- ✅ Vozes vinculadas ao usuário (cada um gerencia as suas)
- ✅ Sistema de planos com limites configuráveis
- ✅ Controle de permissões (usuário só acessa/deleta suas vozes)
- ✅ Soft delete (vozes deletadas ficam no banco para auditoria)

---

## 📊 Estrutura do Banco de Dados

### Tabela `voice_plans`
Armazena os planos de vozes disponíveis.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT | ID do plano |
| `name` | VARCHAR(100) | Nome do plano |
| `description` | TEXT | Descrição do plano |
| `max_voices` | INT | Limite máximo de vozes (ignorado se ilimitado) |
| `is_unlimited` | BOOLEAN | Se o plano é ilimitado |
| `is_active` | BOOLEAN | Se o plano está ativo |
| `created_at` | DATETIME | Data de criação |
| `updated_at` | DATETIME | Data de atualização |

**Planos Padrão:**
- **Plano Básico**: 10 vozes, is_unlimited=0
- **Plano Admin**: vozes ilimitadas, is_unlimited=1

### Tabela `user_voices`
Armazena as vozes personalizadas de cada usuário.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT | ID interno da voz |
| `voice_id` | VARCHAR(64) | ID único da voz (hex) |
| `user_id` | INT | ID do usuário (FK para `users`) |
| `name` | VARCHAR(255) | Nome da voz |
| `filename` | VARCHAR(255) | Nome do arquivo de áudio |
| `reference_text` | TEXT | Texto de referência (opcional) |
| `is_deleted` | BOOLEAN | Se a voz foi deletada (soft delete) |
| `deleted_at` | DATETIME | Data da exclusão |
| `created_at` | DATETIME | Data de criação |
| `updated_at` | DATETIME | Data de atualização |

### Tabela `users` (atualizada)
Adicionado campo `voice_plan_id` para vincular usuário ao plano.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `voice_plan_id` | INT | ID do plano (FK para `voice_plans`) |

---

## 🔧 Instalação e Migração

### 1. Aplicar Scripts SQL

Execute os scripts SQL na ordem:

```bash
# Via MySQL client
mysql -u root -p nome_banco < sql/009_voice_plans.sql
mysql -u root -p nome_banco < sql/010_user_voices.sql
mysql -u root -p nome_banco < sql/011_add_voice_plan_to_users.sql

# Via Docker
docker exec -i mysql_container mysql -u root -p nome_banco < sql/009_voice_plans.sql
docker exec -i mysql_container mysql -u root -p nome_banco < sql/010_user_voices.sql
docker exec -i mysql_container mysql -u root -p nome_banco < sql/011_add_voice_plan_to_users.sql
```

### 2. Migrar Vozes Antigas (se existirem)

Se você tem vozes no formato JSON antigo, use o script de migração:

```bash
# Simular migração (dry-run)
python migrate_voices.py --user-id 1 --dry-run

# Migração real
python migrate_voices.py --user-id 1

# Especificar caminho do JSON
python migrate_voices.py --user-id 1 --json-path /caminho/para/_custom_voices.json
```

**IMPORTANTE:** 
- Defina o `--user-id` apropriado (geralmente 1 para admin)
- O script faz backup do arquivo JSON automaticamente
- Os arquivos de áudio permanecem no mesmo local

### 3. Reiniciar Serviços

```bash
docker compose restart web
docker compose restart tts3
```

---

## 💻 Como Usar (Desenvolvedor)

### Listar Vozes do Usuário

```python
from app import omni_voices as voices_mgr

# Listar vozes do usuário
voices = voices_mgr.list_custom(user_id=1)
# Retorna: [{"id": "abc123", "name": "Voz 1", "filename": "...", "reference_text": "..."}]
```

### Criar Nova Voz

```python
from app import omni_voices as voices_mgr

try:
    voice = voices_mgr.save_custom(
        user_id=1,
        name="Minha Voz",
        content=audio_bytes,
        original_filename="audio.wav",
        reference_text="Texto de referência",
        max_voices=10,  # Do plano do usuário
        is_unlimited=False,  # Do plano do usuário
    )
    print(f"Voz criada: {voice}")
except ValueError as e:
    print(f"Erro: {e}")  # Exemplo: "Limite de 10 vozes atingido"
```

### Obter Informações de Uma Voz

```python
from app import omni_voices as voices_mgr

# Obter voz (verifica propriedade)
voice = voices_mgr.get_custom(voice_id="abc123", user_id=1)
if voice:
    print(f"Nome: {voice['name']}")
    print(f"Arquivo: {voice['filename']}")
```

### Deletar Voz

```python
from app import omni_voices as voices_mgr

# Deletar voz (verifica propriedade)
success = voices_mgr.delete_custom(voice_id="abc123", user_id=1)
if success:
    print("Voz deletada com sucesso")
else:
    print("Voz não encontrada ou sem permissão")
```

### Verificar Limite de Vozes

```python
from app.repositories import user_voices

# Verificar se pode criar mais vozes
can_create = user_voices.check_voice_limit(
    user_id=1,
    max_voices=10,
    is_unlimited=False
)

if can_create:
    print("Pode criar mais vozes")
else:
    print("Limite atingido")
```

---

## 🔌 API REST

### GET `/audio/api/voices`
Lista vozes do usuário + informações do plano.

**Response:**
```json
{
  "custom": [
    {
      "id": "abc123",
      "name": "Voz 1",
      "filename": "omni_u1_voz_1_abc123.wav",
      "reference_text": "Texto de referência"
    }
  ],
  "plan": {
    "name": "Plano Básico",
    "max_voices": 10,
    "is_unlimited": false,
    "current_count": 3,
    "can_create_more": true
  }
}
```

### POST `/audio/api/voices`
Cria nova voz personalizada.

**Form Data:**
- `name` (string): Nome da voz
- `reference_text` (string, opcional): Texto de referência
- `reference_audio` (file): Arquivo de áudio

**Response (Sucesso):**
```json
{
  "voice": {
    "id": "abc123",
    "name": "Minha Voz",
    "filename": "omni_u1_minha_voz_abc123.wav"
  }
}
```

**Response (Erro - Limite Atingido):**
```json
{
  "error": "Limite de 10 vozes atingido para este plano."
}
```

### DELETE `/audio/api/voices/{voice_id}`
Deleta uma voz (soft delete).

**Response:**
```json
{
  "ok": true
}
```

---

## 👥 Planos de Vozes

### Plano Básico
- **Limite:** 10 vozes personalizadas
- **Público:** Usuários comuns
- **Atribuição:** Automática ao criar usuário

### Plano Admin
- **Limite:** Ilimitado
- **Público:** Administradores
- **Atribuição:** Automática para usuários com `is_admin=1`

### Criar Novos Planos

```sql
INSERT INTO voice_plans (name, description, max_voices, is_unlimited, is_active) 
VALUES ('Plano Premium', 'Plano com 50 vozes', 50, 0, 1);
```

### Atribuir Plano a Usuário

```sql
UPDATE users SET voice_plan_id = 3 WHERE id = 5;
```

---

## 🔐 Segurança e Permissões

### Verificações Implementadas

1. **Autenticação**: Apenas usuários logados podem acessar vozes
2. **Permissão**: Requer permissão `omnivoice_audio`
3. **Propriedade**: Usuário só vê/edita/deleta suas próprias vozes
4. **Limite de Plano**: Validação antes de criar nova voz
5. **Soft Delete**: Vozes deletadas permanecem no banco para auditoria

### Exemplo de Fluxo

```
1. Usuário faz login → get_current_user()
2. Sistema verifica permissão → has_permission("omnivoice_audio")
3. Usuário solicita criar voz → voices_mgr.save_custom()
4. Sistema verifica limite → check_voice_limit()
5. Sistema cria voz → user_voices.create_voice()
6. Arquivo salvo em disco → OMNI_VOICES_DIR / filename
```

---

## 📝 Nomenclatura de Arquivos

Os arquivos de áudio agora incluem o ID do usuário:

**Formato:** `omni_u{user_id}_{slug}_{voice_id}{ext}`

**Exemplos:**
- `omni_u1_voz_masculina_abc123.wav`
- `omni_u5_minha_voz_def456.mp3`

Isso facilita:
- Identificação visual do proprietário
- Organização de backups
- Debug e suporte

---

## 🔄 Compatibilidade com Worker TTS3

O worker de geração de áudio (`tts3/worker`) continua funcionando normalmente. A única mudança é que agora ele recebe o `filename` completo (com prefixo de usuário) ao invés de buscar em um índice JSON.

**Nenhuma alteração necessária no worker.**

---

## 🚨 Troubleshooting

### Erro: "Limite de X vozes atingido"
- **Causa:** Usuário atingiu o limite do plano
- **Solução:** Deletar vozes antigas ou atualizar plano do usuário

### Erro: "Voz não encontrada ou sem permissão"
- **Causa:** Usuário tentando acessar voz de outro usuário
- **Solução:** Verificar `voice_id` e propriedade da voz

### Vozes antigas não aparecem
- **Causa:** Migração não foi executada
- **Solução:** Executar `migrate_voices.py` com `--user-id` apropriado

### Erro ao criar voz: "IntegrityError"
- **Causa:** `voice_id` duplicado (muito raro)
- **Solução:** Tentar novamente (novo UUID será gerado)

---

## 📚 Referências

- **Código:**
  - `web/app/omni_voices.py` - Gerenciamento de vozes
  - `web/app/repositories/user_voices.py` - Repositório de vozes
  - `web/app/repositories/voice_plans.py` - Repositório de planos
  - `web/app/routers/audio.py` - API REST

- **Banco de Dados:**
  - `sql/009_voice_plans.sql` - Tabela de planos
  - `sql/010_user_voices.sql` - Tabela de vozes
  - `sql/011_add_voice_plan_to_users.sql` - Atualização de users

- **Migração:**
  - `migrate_voices.py` - Script de migração

---

## 💡 Próximos Passos

- [ ] Interface web para gerenciar planos (admin)
- [ ] Estatísticas de uso de vozes por usuário
- [ ] Backup automático de vozes para Google Drive
- [ ] Compartilhamento de vozes entre usuários
- [ ] Marketplace de vozes pré-configuradas
- [ ] API para criar planos personalizados
