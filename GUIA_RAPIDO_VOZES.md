# 🚀 Guia Rápido - Sistema de Vozes

## ⚡ Início Rápido (5 Minutos)

### 1️⃣ Aplicar Scripts SQL

```bash
# Dentro do diretório do projeto
mysql -u root -p nome_do_banco < sql/009_voice_plans.sql
mysql -u root -p nome_do_banco < sql/010_user_voices.sql
mysql -u root -p nome_do_banco < sql/011_add_voice_plan_to_users.sql
```

**OU via Docker:**

```bash
docker exec -i nome_container_mysql mysql -u root -p nome_do_banco < sql/009_voice_plans.sql
docker exec -i nome_container_mysql mysql -u root -p nome_do_banco < sql/010_user_voices.sql
docker exec -i nome_container_mysql mysql -u root -p nome_do_banco < sql/011_add_voice_plan_to_users.sql
```

### 2️⃣ Reiniciar Serviços

```bash
docker compose restart web
docker compose restart tts3
```

### 3️⃣ Testar

1. Acesse: `http://localhost:8000/audio`
2. Faça login com um usuário
3. Clique em "Vozes" ou "Gerenciar Vozes"
4. Tente criar uma nova voz
5. Veja as informações do plano

✅ **Pronto!** O sistema de vozes está funcionando.

---

## 🔄 Migrar Vozes Antigas (Opcional)

Se você tem vozes no sistema antigo (JSON):

```bash
# 1. Simular migração (ver o que vai acontecer)
python migrate_voices.py --user-id 1 --dry-run

# 2. Migrar de verdade (para o usuário com ID 1)
python migrate_voices.py --user-id 1

# 3. Para outro caminho de JSON
python migrate_voices.py --user-id 1 --json-path /outro/caminho/_custom_voices.json
```

---

## 📊 Verificar Planos

```sql
-- Ver planos criados
SELECT * FROM voice_plans;

-- Ver usuários e seus planos
SELECT u.id, u.email, u.is_admin, vp.name AS plano 
FROM users u 
LEFT JOIN voice_plans vp ON u.voice_plan_id = vp.id;

-- Ver quantas vozes cada usuário tem
SELECT 
    u.id, 
    u.email, 
    COUNT(uv.id) AS total_vozes 
FROM users u 
LEFT JOIN user_voices uv ON u.id = uv.user_id AND uv.is_deleted = 0 
GROUP BY u.id, u.email;
```

---

## 👤 Gerenciar Usuários e Planos

### Atribuir Plano Básico

```sql
UPDATE users SET voice_plan_id = 1 WHERE id = 5;
```

### Atribuir Plano Admin

```sql
UPDATE users SET voice_plan_id = 2 WHERE id = 1;
```

### Criar Novo Plano

```sql
INSERT INTO voice_plans (name, description, max_voices, is_unlimited, is_active) 
VALUES ('Plano Premium', 'Plano com 50 vozes', 50, 0, 1);
```

---

## 🔍 Testar Via API

### Listar Vozes

```bash
curl -X GET http://localhost:8000/audio/api/voices \
  -H "Cookie: session=SEU_TOKEN_AQUI"
```

### Criar Voz

```bash
curl -X POST http://localhost:8000/audio/api/voices \
  -H "Cookie: session=SEU_TOKEN_AQUI" \
  -F "name=Minha Voz Teste" \
  -F "reference_text=Texto de referência" \
  -F "reference_audio=@/caminho/para/audio.wav"
```

### Deletar Voz

```bash
curl -X DELETE http://localhost:8000/audio/api/voices/abc123 \
  -H "Cookie: session=SEU_TOKEN_AQUI"
```

---

## 🐛 Troubleshooting Rápido

### Erro: "Limite de X vozes atingido"
**Solução:** Deletar vozes antigas ou atualizar plano do usuário

```sql
-- Ver vozes do usuário
SELECT * FROM user_voices WHERE user_id = 1 AND is_deleted = 0;

-- Deletar uma voz específica (soft delete)
UPDATE user_voices SET is_deleted = 1, deleted_at = NOW() WHERE voice_id = 'abc123';

-- OU atualizar plano do usuário
UPDATE users SET voice_plan_id = 2 WHERE id = 1;  -- Plano admin (ilimitado)
```

### Erro: "Voz não encontrada"
**Causa:** Voz não existe ou pertence a outro usuário

```sql
-- Verificar dono da voz
SELECT voice_id, user_id, name FROM user_voices WHERE voice_id = 'abc123';
```

### Vozes não aparecem
**Solução:** Verificar se arquivo físico existe

```bash
# Ver arquivos de vozes
ls -la tts3/data/voices/

# Ver registros no banco
SELECT * FROM user_voices WHERE user_id = 1 AND is_deleted = 0;
```

---

## 📝 Principais Comandos SQL

```sql
-- Ver todas as vozes
SELECT * FROM user_voices WHERE is_deleted = 0;

-- Ver vozes de um usuário
SELECT * FROM user_voices WHERE user_id = 1 AND is_deleted = 0;

-- Ver planos
SELECT * FROM voice_plans WHERE is_active = 1;

-- Ver usuários com seus planos
SELECT u.email, vp.name, vp.max_voices, vp.is_unlimited 
FROM users u 
LEFT JOIN voice_plans vp ON u.voice_plan_id = vp.id;

-- Contar vozes por usuário
SELECT user_id, COUNT(*) as total 
FROM user_voices 
WHERE is_deleted = 0 
GROUP BY user_id;

-- Ver vozes deletadas (auditoria)
SELECT * FROM user_voices WHERE is_deleted = 1;
```

---

## 📂 Arquivos Importantes

| Arquivo | Propósito |
|---------|-----------|
| `sql/009_voice_plans.sql` | Cria tabela de planos |
| `sql/010_user_voices.sql` | Cria tabela de vozes |
| `sql/011_add_voice_plan_to_users.sql` | Atualiza tabela users |
| `migrate_voices.py` | Migra vozes antigas |
| `init_voice_plans.py` | Inicializa planos |
| `SISTEMA_VOZES.md` | Documentação completa |

---

## 🎯 Próximos Passos

1. ✅ Aplicar scripts SQL
2. ✅ Reiniciar serviços
3. ✅ Testar criação de vozes
4. ✅ Migrar vozes antigas (se houver)
5. ✅ Verificar limites de planos
6. ✅ Documentar uso para usuários finais

---

## 💡 Dicas

- 💾 **Backup:** Fazer backup do banco antes de aplicar mudanças
- 🔍 **Teste:** Sempre testar em ambiente de desenvolvimento primeiro
- 📊 **Monitorar:** Verificar logs após aplicar mudanças
- 🔐 **Segurança:** Vozes são isoladas por usuário automaticamente
- ♻️ **Soft Delete:** Vozes deletadas ficam no banco (is_deleted=1)

---

## 📞 Mais Informações

- **Documentação Completa:** [SISTEMA_VOZES.md](SISTEMA_VOZES.md)
- **Changelog:** [CHANGELOG_VOZES.md](CHANGELOG_VOZES.md)
- **Resumo:** [RESUMO_ALTERACOES.md](RESUMO_ALTERACOES.md)

---

**Tempo estimado de implementação:** 5-10 minutos ⚡
