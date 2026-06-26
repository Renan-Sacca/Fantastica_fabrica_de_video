# Worker do OmniVoice (k2-fsa) — modelo carregado in-process na GPU.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
# Evita downloads parciais/corrompidos do HF (xet/hf_transfer)
ENV HF_HUB_DISABLE_XET=1
ENV HF_HUB_ENABLE_HF_TRANSFER=0
WORKDIR /app

# Dependências de sistema para áudio
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 git \
    && rm -rf /var/lib/apt/lists/*

# torch + torchaudio casados (CUDA 12.8), conforme instruções do OmniVoice
RUN pip install --no-cache-dir \
    torch==2.8.0+cu128 torchaudio==2.8.0+cu128 \
    --extra-index-url https://download.pytorch.org/whl/cu128

# Demais dependências (omnivoice, rabbit, etc.)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-baixar os pesos do modelo OmniVoice durante o build (com retry + verificação)
COPY download_model.py .
RUN python download_model.py

COPY . .

CMD ["python", "main.py"]
