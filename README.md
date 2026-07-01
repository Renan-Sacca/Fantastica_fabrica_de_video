# 🎬 Fantástica Fábrica de Vídeo

Geração automatizada de vídeos simulando conversas WhatsApp para **TikTok, Reels, Shorts, Instagram e YouTube**.

Os vídeos são gerados 100% em background — sem abrir janelas, sem mover mouse, sem afetar o uso do PC.

---

## ✨ Funcionalidades

### Geração de Vídeos WhatsApp
- 📱 Interface pixel-perfect do WhatsApp
- 💬 Importação de conversas via TXT, JSON ou CSV
- 🎨 Dashboard web para configuração visual
- 📊 Progresso em tempo real com porcentagem
- 🎞️ Renderização frame-a-frame (headless)
- 🎬 Vídeo MP4 com codec H.264
- 📐 Formatos: Vertical (1080×1920), Horizontal (1920×1080), Quadrado (1080×1080)
- 🎵 Música de fundo opcional
- 🤖 Simulação humana (scroll orgânico, pausas naturais)

### Sistema de Vozes OmniVoice (Novo! 🎤)
- 🎙️ **Criação e gerenciamento de vozes personalizadas**
- 🔊 Clonagem de voz a partir de áudio de referência
- 📦 **Sistema de planos com limites configuráveis**
  - **Plano Básico**: até 10 vozes personalizadas por usuário
  - **Plano Admin**: vozes ilimitadas
- 👤 Vozes vinculadas ao usuário (cada usuário gerencia suas próprias vozes)
- 🗄️ Armazenamento em banco de dados (MySQL)
- 🔐 Controle de permissões por usuário
- ♻️ Soft delete (vozes deletadas podem ser recuperadas)

### Infraestrutura
- 🐳 Docker pronto para produção
- 🔐 Sistema de autenticação e permissões
- 📁 Integração com Google Drive
- 🐰 Processamento assíncrono com RabbitMQ

---

## 🚀 Como Usar

### Com Docker (recomendado)

```bash
# 1. Clonar/entrar no diretório do projeto
cd fastastica_fabrica_de_video

# 2. Construir e iniciar
docker compose up -d

# 3. Acessar o dashboard
# Abra no navegador: http://localhost:8000
```

### Sem Docker (local)

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Instalar Playwright + Chromium
playwright install chromium

# 3. Instalar FFmpeg
# Windows: choco install ffmpeg  ou  winget install ffmpeg
# Linux: sudo apt install ffmpeg
# Mac: brew install ffmpeg

# 4. Iniciar a aplicação
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 5. Acessar o dashboard
# Abra no navegador: http://localhost:8000
```

---

## 📝 Formato da Conversa

### TXT (mais simples)

```text
[DATE] 10 de Junho de 2024
[10:30] João: Olá, tudo bem?
[10:31] Maria: Tudo sim! E você?
[10:32] João: Veja esta foto:
[IMAGE] assets/imagens/foto.jpg
[10:33] Maria: Que linda! 😍
[EMOJI] ❤️
```

**Regras:**
- O **primeiro nome** que aparecer será tratado como o **contato** (mensagens recebidas)
- O **segundo nome** será tratado como **você** (mensagens enviadas)
- Comandos especiais: `[IMAGE]`, `[EMOJI]`, `[AUDIO]`, `[DATE]`

### JSON

```json
[
    {"sender": "João", "text": "Olá!", "time": "10:30", "type": "text"},
    {"sender": "me", "text": null, "time": "10:31", "type": "image", "media_path": "foto.jpg"},
    {"sender": "me", "text": "😍", "time": "10:32", "type": "emoji"}
]
```

### CSV

```csv
time,sender,message,type,media_path
10:30,João,Olá!,text,
10:31,me,,image,foto.jpg
```

---

## 📐 Formatos de Vídeo

| Formato | Resolução | Uso |
|---------|-----------|-----|
| Vertical | 1080×1920 | TikTok, Reels, Shorts |
| Horizontal | 1920×1080 | YouTube |
| Quadrado | 1080×1080 | Instagram Feed |

---

## 🏗️ Estrutura do Projeto

```
fastastica_fabrica_de_video/
├── api/                      # Backend FastAPI
│   ├── main.py               # App + rotas
│   ├── parser.py             # Parser de conversas
│   ├── models.py             # Modelos Pydantic
│   ├── jobs.py               # Gerenciamento de jobs
│   └── config.py             # Configurações
├── renderer/                 # Motor de renderização
│   ├── engine.py             # Playwright + frames
│   ├── animator.py           # Timeline + easing
│   ├── ffmpeg_composer.py    # Composição de vídeo
│   └── utils.py              # Utilitários
├── frontend/whatsapp/        # Clone do WhatsApp (headless)
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── templates/                # Dashboard web
│   └── dashboard.html
├── static/                   # Assets do dashboard
│   ├── dashboard.css
│   └── dashboard.js
├── conversations/            # Conversas de entrada
├── assets/imagens/           # Imagens para conversas
├── output/                   # Vídeos gerados
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🔌 API REST

Também disponível para automação:

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/render` | Iniciar renderização |
| `GET` | `/api/jobs` | Listar jobs |
| `GET` | `/api/jobs/{id}` | Status de um job |
| `GET` | `/api/jobs/{id}/stream` | Progresso em tempo real (SSE) |
| `GET` | `/api/download/{id}` | Download do vídeo |
| `DELETE` | `/api/jobs/{id}` | Remover job |

---

## ⚙️ Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `MAX_CONCURRENT_RENDERS` | `2` | Renders simultâneos |

---

## 📄 Licença

Projeto de uso pessoal/educacional.
