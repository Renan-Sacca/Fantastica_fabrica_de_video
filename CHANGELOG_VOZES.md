# 📝 Changelog - Sistema de Vozes

## 🎉 Versão 2.0 - Sistema de Vozes com Planos

**Data:** 2026-07-01

### ✨ Novas Funcionalidades

#### 🎤 Sistema de Vozes Baseado em Banco de Dados
- Vozes agora são armazenadas no MySQL ao invés de arquivo JSON
- Cada usuário possui suas próprias vozes personalizadas
- Controle de propriedade: usuários só podem acessar/editar/deletar suas vozes
- Soft delete: vozes deletadas ficam no banco para auditoria

#### 📦 Sistema de Planos
- **Plano Básico**: limite de 10 vozes por usuário
- **Plano Admin**: vozes ilimitadas (para administradores)
- Validação automática ao criar novas vozes
- Mensagens de erro claras quando limite é atingido

#### 🔐 Segurança Aprimorada
- Verificação de propriedade em todas as operações
- Vozes não podem ser acessadas por outros usuários
- Integração com sistema de permissões existente
- Logs de auditoria para criação/exclusão de vozes

---

### 📊 Banco de Dados

#### Novas Tabelas

**`voice_plans`** - Planos de vozes disponíveis
```sql
CREATE TABLE voice_plans (
    id INT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    max_voices INT NOT NULL DEFAULT 10,
    is_unlimited BOOLEAN NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

**`user_voices`** - Vozes personalizadas por usuário
```sql
CREATE TABLE user_voices (
    id INT PRIMARY KEY AUTO_INCREMENT,
    voice_id VARCHAR(64) UNIQUE NOT NULL,
    user_id INT NOT NULL,
    name VARCHAR(255) NOT NULL,
    filename VARCHAR(255) NOT NULL,
    reference_text TEXT,
    is_deleted BOOLEAN NOT NULL DEFAULT 0,
    deleted_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### Tabelas Modificadas

**`users`** - Adicionado campo de plano
```sql
ALTER TABLE users ADD COLUMN voice_plan_id INT;
ALTER TABLE users ADD FOREIGN KEY (voice_plan_id) REFERENCES voice_plans(id);
```

---

### 📁 Arquivos Criados/Modificados

#### ✅ Novos Arquivos

##### Scripts SQL
- `sql/009_voice_plans.sql` - Cria tabela de planos
- `sql/010_user_voices.sql` - Cria tabela de vozes
- `sql/011_add_voice_plan_to_users.sql` - Atualiza tabela users
- `sql/README.md` - Documentação dos scripts SQL

##### Models SQLAlchemy
- `web/app/models/voice_plan.py` - Model de planos
- `web/app/models/user_voice.py` - Model de vozes

##### Repositórios
- `web/app/repositories/voice_plans.py` - CRUD de planos
- `web/app/repositories/user_voices.py` - CRUD de vozes

##### Scripts Utilitários
- `migrate_voices.py` - Migração de vozes antigas (JSON → MySQL)
- `init_voice_plans.py` - Inicialização dos planos padrão

##### Documentação
- `SISTEMA_VOZES.md` - Documentação completa do sistema
- `CHANGELOG_VOZES.md` - Este arquivo

#### 🔄 Arquivos Modificados

- **`web/app/omni_voices.py`**
  - ❌ Removido: Sistema baseado em arquivo JSON (`_custom_index.json`)
  - ✅ Adicionado: Integração com banco de dados MySQL
  - ✅ Adicionado: Validação de limites de plano
  - ✅ Adicionado: Verificação de propriedade
  - ✅ Adicionado: Parâmetro `user_id` em todas as funções

- **`web/app/routers/audio.py`**
  - ✅ Atualizado: Endpoint GET `/api/voices` retorna informações do plano
  - ✅ Atualizado: Endpoint POST `/api/voices` valida limite de vozes
  - ✅ Atualizado: Endpoint DELETE `/api/voices/{id}` verifica propriedade
  - ✅ Atualizado: Geração de áudio valida propriedade da voz

- **`web/app/models/user.py`**
  - ✅ Adicionado: Campo `voice_plan_id`
  - ✅ Adicionado: Relationship com `VoicePlan`
  - ✅ Atualizado: Método `to_dict()` inclui informações do plano

- **`README.md`**
  - ✅ Adicionado: Seção sobre sistema de vozes

---

### 🔌 Mudanças na API

#### GET `/audio/api/voices`

**Antes:**
```json
{
  "custom": [
    {"id": "abc", "name": "Voz 1", "filename": "...", "reference_text": "..."}
  ]
}
```

**Agora:**
```json
{
  "custom": [
    {"id": "abc", "name": "Voz 1", "filename": "...", "reference_text": "..."}
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

#### POST `/audio/api/voices`

**Nova resposta de erro:**
```json
{
  "error": "Limite de 10 vozes atingido para este plano."
}
```
(Status code: 400)

#### DELETE `/audio/api/voices/{voice_id}`

**Nova resposta de erro:**
```json
{
  "error": "Voz não encontrada ou sem permissão."
}
```
(Status code: 404)

---

### 🔄 Migração

#### Passos para Atualizar

1. **Aplicar scripts SQL:**
   ```bash
   mysql -u root -p banco < sql/009_voice_plans.sql
   mysql -u root -p banco < sql/010_user_voices.sql
   mysql -u root -p banco < sql/011_add_voice_plan_to_users.sql
   ```

2. **Inicializar planos (opcional, já incluído nos scripts):**
   ```bash
   python init_voice_plans.py
   ```

3. **Migrar vozes antigas (se existirem):**
   ```bash
   # Simular primeiro (recomendado)
   python migrate_voices.py --user-id 1 --dry-run
   
   # Migrar de verdade
   python migrate_voices.py --user-id 1
   ```

4. **Reiniciar serviços:**
   ```bash
   docker compose restart web
   docker compose restart tts3
   ```

---

### 🗑️ Removido/Deprecado

#### ❌ Arquivo JSON de Vozes
- `tts3/data/voices/_custom_voices.json` - **Não é mais utilizado**
- Sistema antigo de índice JSON foi completamente substituído
- Arquivos existentes devem ser migrados usando `migrate_voices.py`

#### ❌ Funções Modificadas
As seguintes funções em `omni_voices.py` mudaram de assinatura:

```python
# ANTES
list_custom() → list[dict]
save_custom(name, content, filename, reference_text) → dict
get_custom(voice_id) → dict | None
delete_custom(voice_id) → bool

# AGORA
list_custom(user_id) → list[dict]
save_custom(user_id, name, content, filename, reference_text, max_voices, is_unlimited) → dict
get_custom(voice_id, user_id=None) → dict | None
delete_custom(voice_id, user_id) → bool
```

**⚠️ Código que usa essas funções precisa ser atualizado!**

---

### 🐛 Correções

- Resolvido: Vozes compartilhadas entre usuários (agora isoladas)
- Resolvido: Sem limite de criação de vozes (agora controlado por plano)
- Resolvido: Arquivos de vozes sem identificação do proprietário (agora incluem user_id)
- Resolvido: Impossibilidade de auditoria (soft delete implementado)

---

### 🎯 Melhorias Futuras

- [ ] Interface web para gerenciar planos (admin)
- [ ] Dashboard de uso de vozes por usuário
- [ ] Backup automático para Google Drive
- [ ] Compartilhamento de vozes entre usuários
- [ ] Marketplace de vozes
- [ ] API para criar planos personalizados
- [ ] Importação em lote de vozes
- [ ] Categorização de vozes (masculina, feminina, infantil, etc.)
- [ ] Preview de vozes antes de usar
- [ ] Histórico de uso de cada voz

---

### 📚 Documentação

Para mais detalhes, consulte:
- **[SISTEMA_VOZES.md](SISTEMA_VOZES.md)** - Documentação completa do sistema
- **[sql/README.md](sql/README.md)** - Guia de scripts SQL
- **[README.md](README.md)** - Documentação geral do projeto

---

### 👥 Contribuidores

- Sistema desenvolvido em 01/07/2026
- Migração de JSON para MySQL
- Implementação de sistema de planos

---

### ⚠️ Breaking Changes

**ATENÇÃO:** Esta atualização contém mudanças incompatíveis com versão anterior:

1. **Assinatura de funções alterada** em `omni_voices.py`
2. **Estrutura de dados modificada** (JSON → MySQL)
3. **Nomenclatura de arquivos** inclui ID do usuário
4. **API modificada** (novos campos em responses)

**Impacto:** Código existente que usa diretamente `omni_voices.py` precisa ser atualizado.

**Recomendação:** Testar em ambiente de desenvolvimento antes de aplicar em produção.
