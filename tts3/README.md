# Gerador de Áudio 3 — OmniVoice (k2-fsa)

Terceiro gerador de TTS, isolado, com **GPU NVIDIA**, usando o
[OmniVoice](https://github.com/k2-fsa/OmniVoice) — TTS zero-shot multilíngue (600+ idiomas),
com clonagem de voz, voice design e controle fino. A **tela** fica no site (`web/`, menu "Áudio (Omni)").
Os módulos `tts` (XTTS) e `tts2` (Fish) continuam intactos.

> Ainda **não** integra com banco de dados nem Google Drive. É um ambiente de teste.

## Componentes

| Serviço       | Container             | Função                                                  |
|---------------|-----------------------|---------------------------------------------------------|
| `omni-worker` | `fabrica-omni-worker` | Carrega o OmniVoice na GPU e consome a fila própria.     |

- **Fila RabbitMQ:** `omni_audio_jobs`
- **Exchange de progresso (SSE):** `omni_audio_progress`
- **Pasta compartilhada:** `tts3/data` (`voices/` = áudios de referência, `outputs/` = `.wav` gerados a 24kHz)

O site monta esta mesma pasta (`../tts3/data` → `/app/tts3_audio`) para ler as vozes e servir os áudios.

## Modos de geração (abas na tela)

1. **Clonagem de voz** — áudio de referência (3–10s) + transcrição (opcional; sem ela o Whisper transcreve).
2. **Voice Design** — descreve a voz por atributos (gênero, idade, tom, sotaque, dialeto, sussurro), sem áudio.
3. **Auto** — o modelo escolhe uma voz automaticamente.

## Parâmetros expostos na tela

- **Decodificação:** `num_step`, `denoise`, `guidance_scale`, `t_shift`
- **Amostragem:** `position_temperature`, `class_temperature`, `layer_penalty_factor`
- **Duração/Velocidade:** `speed`, `duration`
- **Pré/Pós:** `preprocess_prompt`, `postprocess_output`
- **Texto longo:** `audio_chunk_duration`, `audio_chunk_threshold`
- **Idioma:** `language_id` (opcional)
- **Símbolos não-verbais:** `[laughter]`, `[sigh]`, etc. (botões que inserem no texto)

## Pré-requisitos

- Docker + Docker Compose
- GPU NVIDIA com drivers + **NVIDIA Container Toolkit** (cabe em 8GB; o projeto cita teste em 4GB).

## Como rodar

```bash
cd tts3
cp .env.example .env   # ajuste o RABBITMQ_URL se necessário
docker compose up --build

# Em seguida, o site (com a aba "Áudio (Omni)")
cd ../web
docker compose up --build
```

> O primeiro build instala o torch (cu128) e baixa os pesos do OmniVoice. Pode demorar.
> Se não informar a transcrição na clonagem, o Whisper é baixado na 1ª vez (fica no cache).

Acesse o site em **http://localhost:8000** e abra **Áudio (Omni)**.
