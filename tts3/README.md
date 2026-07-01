# Gerador de Áudio — OmniVoice (k2-fsa)

Gerador de TTS do projeto, isolado, com **GPU NVIDIA**, usando o
[OmniVoice](https://github.com/k2-fsa/OmniVoice) — TTS zero-shot multilíngue (600+ idiomas),
com clonagem de voz, voice design e controle fino. A **tela** fica no site (`web/`, menu "Áudio").

Agora integra com **MySQL** (histórico) e **Google Drive** (armazenamento dos áudios).

## Componentes

| Serviço       | Container             | Função                                                           |
|---------------|-----------------------|------------------------------------------------------------------|
| `omni-worker` | `fabrica-omni-worker` | Gera o áudio na GPU, salva no Drive e atualiza o MySQL.           |

- **Fila RabbitMQ:** `omni_audio_jobs`
- **Exchange de progresso (SSE):** `omni_audio_progress`
- **Permissão necessária (no site):** `omnivoice_audio`
- **Pasta compartilhada:** `tts3/data` (`voices/` = referências, `outputs/` = `.wav` gerados a 24kHz)
- **Drive:** `FantasticaFabricaDeVideo/OmniVoiceAudios/Criados/{titulo}-{job_id}/`
- **MySQL:** tabela `omnivoice_audio_jobs`

## Fluxo

1. O site cria a pasta no Drive + `metadata.json`, registra o job no MySQL e publica na fila.
2. O worker gera o `.wav`, salva localmente (para o player), faz upload ao Drive (link público)
   e atualiza o MySQL (status, `audio_drive_id`, `audio_url`).
3. O progresso aparece na tela via SSE; o histórico por usuário fica em **Áudio → Histórico**.

## Modos de geração (abas na tela)

1. **Clonagem de voz** — áudio de referência (3–10s) + transcrição (opcional; sem ela o Whisper transcreve).
2. **Voice Design** — gênero, idade, tom, sotaque, dialeto, sussurro (sem áudio).
3. **Auto** — voz automática.

## Parâmetros expostos

`num_step`, `denoise`, `guidance_scale`, `t_shift`, `position_temperature`,
`class_temperature`, `layer_penalty_factor`, `speed`, `duration`,
`audio_chunk_duration`, `audio_chunk_threshold`, `language_id`,
e símbolos não-verbais (`[laughter]`, `[sigh]`, ...).

## Pré-requisitos

- Docker + Docker Compose, GPU NVIDIA + NVIDIA Container Toolkit (cabe em 8GB).
- `token.json` e `credentials.json` na raiz do projeto (já usados pelos outros módulos).
- Acesso ao MySQL (configurado no `.env`).

## Como rodar

```bash
cd tts3
cp .env.example .env   # ajuste RABBITMQ_URL e MYSQL_* se necessário
docker compose up --build

cd ../web
docker compose up --build
```

> Dê a permissão `omnivoice_audio` ao usuário em **Usuários** (admin) para o menu "Áudio" aparecer.

Acesse o site em **http://localhost:8000** e abra **Áudio**.
