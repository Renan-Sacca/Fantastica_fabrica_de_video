FROM python:3.12-slim-bookworm

# Instalar dependências do sistema + dependências do Playwright/Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-color-emoji \
    fonts-roboto \
    fonts-dejavu-core \
    fonts-unifont \
    # Dependências do Chromium (Playwright)
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libatspi2.0-0 \
    libwayland-client0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

# Diretório de trabalho
WORKDIR /app

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Playwright Chromium SEM --with-deps (deps já instaladas acima)
RUN playwright install chromium

# Copiar código do projeto
COPY . .

# Criar diretórios necessários
RUN mkdir -p output uploads conversations assets/imagens

# Expor porta da API
EXPOSE 8000

# Comando padrão
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
