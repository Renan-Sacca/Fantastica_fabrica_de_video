FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Instalar ffmpeg e limpar cache
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código fonte
COPY . .

# Comando para iniciar o worker
CMD ["python", "main.py"]
