FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Instalar ffmpeg e limpar cache
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
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

# Comando para iniciar o worker
CMD ["python", "main.py"]
