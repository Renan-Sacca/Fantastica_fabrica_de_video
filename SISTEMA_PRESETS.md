# 🎛️ Sistema de Presets de Parâmetros Avançados

## 📋 Visão Geral

Sistema para salvar e carregar configurações de parâmetros avançados de geração de áudio, com os mesmos limites dos planos de vozes:
- **Plano Básico**: até 10 presets
- **Plano Admin**: presets ilimitados

---

## ✨ Funcionalidades

### 💾 Salvar Configurações
- Salva todos os parâmetros avançados atuais
- Nome personalizado para cada preset
- Vinculado ao usuário
- Respeita limite do plano

### 📂 Carregar Configurações
- Lista de presets salvos no dropdown
- Carrega instantaneamente todos os parâmetros
- Feedback visual ao carregar

### 🗑️ Gerenciar Presets
- Soft delete (recuperável)
- Verifica propriedade antes de deletar
- Isolamento por usuário

---

## 📊 Banco de Dados

### Tabela `audio_presets`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT | ID interno |
| `preset_id` | VARCHAR(64) | ID único (hex) |
| `user_id` | INT | Usuário proprietário |
| `name` | VARCHAR(255) | Nome do preset |
| `description` | TEXT | Descrição (opcional) |
| **Parâmetros** | | |
| `num_step` | INT | Passos de difusão |
| `guidance_scale` | FLOAT | Força do guia |
| `t_shift` | FLOAT | Deslocamento temporal |
| `position_temperature` | FLOAT | Temperatura de posição |
| `class_temperature` | FLOAT | Temperatura de classe |
| `layer_penalty_factor` | FLOAT | Fator de penalidade |
| `speed` | FLOAT | Velocidade da fala |
| `duration` | FLOAT | Duração fixa (opcional) |
| `audio_chunk_duration` | FLOAT | Duração de cada pedaço |
| `audio_chunk_threshold` | FLOAT | Limite para dividir |
| `language_id` | VARCHAR(10) | Código do idioma |
| `denoise` | BOOLEAN | Remove ruídos |
| `preprocess_prompt` | BOOLEAN | Limpa áudio de referência |
| `postprocess_output` | BOOLEAN | Remove silêncios |
| **Controle** | | |
| `is_deleted` | BOOLEAN | Soft delete |
| `deleted_at` | DATETIME | Data da exclusão |
| `created_at` | DATETIME | Data de criação |
| `updated_at` | DATETIME | Data de atualização |

---

## 📝 Explicações dos Parâmetros (Melhoradas)

### 🔢 num_step
**Descrição:** Passos de difusão (16-64)  
**O que faz:** Controla quantas iterações o modelo faz para gerar o áudio  
**Valores:** Maiores = melhor qualidade mas mais lento  
**Padrão:** 32  
**Recomendação:** 
- 16 para rápido (teste)
- 32 para qualidade balanceada
- 64 para máxima qualidade

### 🎯 guidance_scale
**Descrição:** Força do guia (0.0-5.0)  
**O que faz:** Controla quanto o modelo segue as instruções  
**Padrão:** 2.0  
**Recomendação:** Valores altos = mais fidelidade às instruções

### 📊 t_shift
**Descrição:** Deslocamento temporal (0.0-1.0)  
**O que faz:** Ajusta o agendamento de ruído  
**Padrão:** 0.1  
**Recomendação:** Raramente precisa alterar

### 🎲 position_temperature
**Descrição:** Temperatura de posição (0.0-10.0)  
**O que faz:** Controla variação na geração  
**Valores:**
- 0 = determinístico (sempre igual)
- Maior = mais variação
**Padrão:** 5.0

### 🎲 class_temperature
**Descrição:** Temperatura de classe (0.0-10.0)  
**O que faz:** Controla variação de tokens  
**Valores:** 0 = determinístico  
**Padrão:** 0.0

### ⚖️ layer_penalty_factor
**Descrição:** Fator de penalidade (0.0-10.0)  
**O que faz:** Penaliza camadas específicas  
**Padrão:** 5.0

### ⏩ speed
**Descrição:** Velocidade da fala (0.5-2.0)  
**O que faz:** Acelera ou desacelera a fala  
**Valores:**
- 1.0 = normal
- > 1.0 = mais rápido
- < 1.0 = mais lento
**Exemplo:** 1.2 = 20% mais rápido

### ⏱️ duration
**Descrição:** Duração fixa em segundos  
**O que faz:** Força uma duração específica  
**Nota:** Se definido, ignora o parâmetro `speed`  
**Uso:** Deixe vazio para duração automática

### ✂️ audio_chunk_duration
**Descrição:** Duração de cada pedaço de áudio (segundos)  
**O que faz:** Divide textos longos em pedaços menores  
**Padrão:** 15s

### 📏 audio_chunk_threshold
**Descrição:** Limite para dividir em pedaços (segundos)  
**O que faz:** Se áudio estimado > threshold, divide  
**Padrão:** 30s

### 🌍 language_id
**Descrição:** Código do idioma no formato ISO (opcional)  
**O que faz:** Força um idioma/localidade específica  
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
**Nota:** Auto-detecta se vazio (recomendado)

### 🔇 denoise
**Descrição:** Remove ruídos de fundo  
**O que faz:** Limpa a voz gerada  
**Recomendação:** ✅ Ativado (padrão)

### 🧹 preprocess_prompt
**Descrição:** Limpa áudio de referência  
**O que faz:** Remove ruídos do áudio antes de clonar  
**Recomendação:** ✅ Ativado (padrão)

### ✂️ postprocess_output
**Descrição:** Remove silêncios inicial e final  
**O que faz:** Corta silêncios desnecessários  
**Recomendação:** ✅ Ativado (padrão)

---

## 🔌 API REST

### GET `/audio/api/presets`
Lista presets do usuário + informações do plano.

**Response:**
```json
{
  "presets": [
    {
      "preset_id": "abc123",
      "name": "Voz rápida",
      "description": "Configuração para narração rápida",
      "params": {
        "num_step": 16,
        "speed": 1.3,
        "denoise": true,
        ...
      },
      "created_at": "2026-07-01T10:00:00"
    }
  ],
  "plan": {
    "name": "Plano Básico",
    "max_presets": 10,
    "is_unlimited": false,
    "current_count": 3,
    "can_create_more": true
  }
}
```

### POST `/audio/api/presets`
Cria novo preset.

**Request:**
```json
{
  "name": "Minha Config",
  "description": "Descrição opcional",
  "params": {
    "num_step": 32,
    "speed": 1.0,
    "denoise": true,
    ...
  }
}
```

**Response (Sucesso):**
```json
{
  "preset": {
    "preset_id": "abc123",
    "name": "Minha Config",
    ...
  }
}
```

**Response (Erro - Limite):**
```json
{
  "error": "Limite de 10 presets atingido para este plano."
}
```

### DELETE `/audio/api/presets/{preset_id}`
Deleta um preset (soft delete).

**Response:**
```json
{
  "ok": true
}
```

---

## 💻 Interface

### Dropdown de Presets
- Localizado acima dos parâmetros avançados
- Lista todos os presets salvos
- Selecionar = carrega instantaneamente

### Botão Salvar
- Localizado ao lado do dropdown
- Pede nome para o preset
- Salva configuração atual
- Valida limite do plano

### Feedback Visual
- ✅ Toast de sucesso ao salvar
- ✅ Toast de sucesso ao carregar
- ❌ Toast de erro se limite atingido
- ℹ️ Mensagens claras e em português

---

## 📈 Casos de Uso

### 1. Narração Rápida
```json
{
  "name": "Narração Rápida",
  "params": {
    "num_step": 16,
    "speed": 1.3,
    "denoise": true
  }
}
```

### 2. Qualidade Máxima
```json
{
  "name": "Qualidade Máxima",
  "params": {
    "num_step": 64,
    "guidance_scale": 3.0,
    "denoise": true,
    "postprocess_output": true
  }
}
```

### 3. Fala Lenta e Clara
```json
{
  "name": "Fala Lenta",
  "params": {
    "num_step": 32,
    "speed": 0.8,
    "denoise": true
  }
}
```

---

## 🔒 Segurança

- ✅ Presets isolados por usuário
- ✅ Verificação de propriedade ao deletar
- ✅ Validação de limite do plano
- ✅ Soft delete para auditoria
- ✅ Integração com sistema de permissões

---

## 📊 Estatísticas

### Arquivos Criados
- `sql/012_audio_presets.sql` - Script SQL
- `web/app/models/audio_preset.py` - Model
- `web/app/repositories/audio_presets.py` - Repositório

### Arquivos Modificados
- `web/app/models/__init__.py` - Registro do model
- `web/app/models/voice_plan.py` - Adicionado max_presets
- `web/app/routers/audio.py` - 3 novas rotas de API
- `web/templates/audio/create.html` - UI de presets
- `web/static/audio.js` - Funções de presets

### Linhas de Código
- ~300 linhas Python
- ~50 linhas SQL
- ~100 linhas JavaScript
- ~50 linhas HTML/CSS

---

## 🚀 Como Usar

### 1. Configurar Parâmetros
- Abra "Parâmetros avançados"
- Ajuste os valores desejados

### 2. Salvar Preset
- Clique em "💾 Salvar configuração"
- Digite um nome
- Confirme

### 3. Carregar Preset
- Selecione no dropdown
- Parâmetros são carregados automaticamente

### 4. Gerar Áudio
- Use os parâmetros carregados
- Clique em "Gerar áudio"

---

## ✅ Checklist

- [x] Tabela SQL criada
- [x] Model criado
- [x] Repositório criado
- [x] Rotas de API criadas
- [x] UI implementada
- [x] JavaScript funcional
- [x] Validação de limites
- [x] Explicações melhoradas
- [x] Isolamento por usuário
- [x] Soft delete
- [x] Documentação completa

---

**Data:** 01/07/2026  
**Status:** ✅ 100% Completo
