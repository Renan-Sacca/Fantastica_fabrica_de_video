FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Instalar ffmpeg, libsndfile (librosa), Xvfb (display virtual p/ WebGL na GPU)
# e drivers Mesa (o d3d12/Dozen conversa com a GPU NVIDIA via /dev/dxg no WSL2).
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg libsndfile1 xvfb \
        libgl1-mesa-dri libglx-mesa0 libegl-mesa0 mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pré-baixar os modelos do PaddleOCR (detecção, classificação de ângulo e
# reconhecimento em português) já durante o build. Assim o container NÃO
# baixa os modelos toda vez que sobe / processa um job.
RUN python -c "from paddleocr import PaddleOCR; PaddleOCR(use_angle_cls=True, lang='pt', show_log=False)"

# Copiar o código fonte
COPY . .

# Inicia via entrypoint que sobe o Xvfb (display virtual) antes do worker.
# O Chromium precisa rodar em modo "headful" para usar a GPU no WebGL — em
# headless ele cai no SwiftShader (CPU). Sem GPU, o renderer faz fallback
# automático para SwiftShader.
RUN chmod +x /app/entrypoint.sh
CMD ["bash", "/app/entrypoint.sh"]
