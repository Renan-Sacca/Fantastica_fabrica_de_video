# 🔧 Correção - Formato do Código de Idioma

## 🐛 Problema Identificado

**Antes:** A documentação e exemplos mostravam códigos de idioma simples (`pt`, `en`, `zh`)  
**Correto:** O formato padrão ISO é `idioma-PAÍS` (`pt-BR`, `en-US`, `zh-CN`)

---

## ✅ Correções Realizadas

### 1. Interface (HTML)
**Arquivo:** `web/templates/audio/create.html`

**Antes:**
```html
<input type="text" id="p-language_id" placeholder="ex: pt, en, zh">
<div class="hint">🌍 Código do idioma (opcional). Ex: pt, en, es, fr, zh, ja...</div>
```

**Agora:**
```html
<input type="text" id="p-language_id" placeholder="ex: pt-BR, en-US, es-ES">
<div class="hint">🌍 Código do idioma no formato ISO (opcional). 
Ex: pt-BR (português Brasil), en-US (inglês EUA), es-ES (espanhol), 
fr-FR (francês), zh-CN (chinês), ja-JP (japonês). Auto-detecta se vazio.</div>
```

### 2. Documentação
**Arquivo:** `SISTEMA_PRESETS.md`

**Antes:**
```markdown
### 🌍 language_id
**Descrição:** Código do idioma (opcional)  
**Exemplos:** pt, en, es, fr, zh, ja  
```

**Agora:**
```markdown
### 🌍 language_id
**Descrição:** Código do idioma no formato ISO (opcional)  
**Formato:** código-PAÍS (ISO 639-1 + ISO 3166-1)  
**Exemplos:** 
- `pt-BR` - Português do Brasil
- `pt-PT` - Português de Portugal
- `en-US` - Inglês americano
- `en-GB` - Inglês britânico
- `es-ES` - Espanhol da Espanha
- `es-MX` - Espanhol do México
- `fr-FR` - Francês da França
- `zh-CN` - Chinês simplificado
- `ja-JP` - Japonês
```

### 3. Banco de Dados
**Arquivo:** `sql/013_update_language_id_comment.sql`

Adicionado comentário ao campo:
```sql
ALTER TABLE `audio_presets` 
MODIFY COLUMN `language_id` VARCHAR(10) NULL 
COMMENT 'Código ISO do idioma (ex: pt-BR, en-US, es-ES)';
```

### 4. Nova Documentação
**Arquivo:** `CODIGOS_IDIOMA.md` (novo)

Criado documento completo com:
- ✅ Lista de 50+ códigos de idioma mais comuns
- ✅ Explicação do formato ISO
- ✅ Exemplos práticos de uso
- ✅ Quando usar auto-detecção vs código específico
- ✅ Referências aos padrões ISO

---

## 📊 Formato Correto

### Padrão ISO
```
idioma-PAÍS
```

Onde:
- **idioma** = código ISO 639-1 (2 letras minúsculas)
- **PAÍS** = código ISO 3166-1 (2 letras MAIÚSCULAS)
- **hífen** = separador obrigatório

### Exemplos Válidos
✅ `pt-BR` - Correto  
✅ `en-US` - Correto  
✅ `zh-CN` - Correto  

❌ `pt` - Incompleto  
❌ `pt_BR` - Separador errado  
❌ `ptBR` - Sem separador  
❌ `PT-BR` - Maiúsculas incorretas  
❌ `pt-br` - Minúsculas incorretas  

---

## 🌍 Principais Códigos

### América
- `pt-BR` 🇧🇷 Português (Brasil)
- `en-US` 🇺🇸 Inglês (EUA)
- `en-CA` 🇨🇦 Inglês (Canadá)
- `fr-CA` 🇨🇦 Francês (Canadá)
- `es-MX` 🇲🇽 Espanhol (México)
- `es-AR` 🇦🇷 Espanhol (Argentina)

### Europa
- `pt-PT` 🇵🇹 Português (Portugal)
- `en-GB` 🇬🇧 Inglês (Reino Unido)
- `es-ES` 🇪🇸 Espanhol (Espanha)
- `fr-FR` 🇫🇷 Francês (França)
- `de-DE` 🇩🇪 Alemão (Alemanha)
- `it-IT` 🇮🇹 Italiano (Itália)

### Ásia
- `zh-CN` 🇨🇳 Chinês simplificado
- `zh-TW` 🇹🇼 Chinês tradicional
- `ja-JP` 🇯🇵 Japonês
- `ko-KR` 🇰🇷 Coreano
- `hi-IN` 🇮🇳 Hindi
- `th-TH` 🇹🇭 Tailandês

---

## 💡 Quando Usar

### Auto-detecção (Recomendado)
```json
{
  "text": "Olá, tudo bem?",
  "language_id": ""  // vazio = auto-detecta
}
```

**Vantagens:**
- ✅ Funciona muito bem
- ✅ Não precisa especificar
- ✅ Detecta múltiplos idiomas

**Use quando:**
- Texto em um único idioma claro
- Não importa sotaque específico
- Primeira tentativa

### Código Específico
```json
{
  "text": "Olá, tudo bem?",
  "language_id": "pt-BR"
}
```

**Vantagens:**
- ✅ Garante sotaque correto
- ✅ Melhor para nomes próprios
- ✅ Útil em textos multilíngues

**Use quando:**
- Precisa sotaque específico (pt-BR vs pt-PT)
- Texto tem palavras em vários idiomas
- Pronúncia de nomes é importante

---

## 🎯 Exemplos Práticos

### Português Brasil vs Portugal
```javascript
// Brasil
{
  text: "O carro está na garagem",
  language_id: "pt-BR"  // sotaque brasileiro
}

// Portugal
{
  text: "O carro está na garagem",
  language_id: "pt-PT"  // sotaque português
}
```

### Inglês Americano vs Britânico
```javascript
// Americano
{
  text: "Color, center, analyze",
  language_id: "en-US"  // pronúncia americana
}

// Britânico
{
  text: "Colour, centre, analyse",
  language_id: "en-GB"  // pronúncia britânica
}
```

### Texto Multilíngue
```javascript
{
  text: "Welcome to Brasil! Bem-vindo ao nosso país!",
  language_id: "pt-BR"  // força português brasileiro
}
```

---

## 📝 Checklist de Atualização

- [x] Corrigido placeholder do input
- [x] Atualizado hint explicativo
- [x] Atualizada documentação SISTEMA_PRESETS.md
- [x] Adicionado comentário no banco de dados
- [x] Criado documento CODIGOS_IDIOMA.md
- [x] Exemplos atualizados com formato correto

---

## 🚀 Como Aplicar

As alterações já estão no código! Basta reiniciar o serviço:

```bash
docker compose -f web/docker-compose.yml restart
```

---

## 📚 Documentação Relacionada

- **CODIGOS_IDIOMA.md** - Lista completa de códigos
- **SISTEMA_PRESETS.md** - Documentação de presets
- **ISO 639-1** - Padrão de códigos de idioma
- **ISO 3166-1** - Padrão de códigos de país

---

**Data:** 01/07/2026  
**Tipo:** Correção de Documentação + Interface  
**Status:** ✅ Corrigido
