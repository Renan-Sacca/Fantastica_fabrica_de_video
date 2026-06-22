FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Instalar dependências do sistema: Xvfb + x11vnc + noVNC + supervisor
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    x11vnc \
    supervisor \
    git \
    && rm -rf /var/lib/apt/lists/*

# Instalar noVNC (interface web para VNC)
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone --depth 1 https://github.com/novnc/websockify.git /opt/novnc/utils/websockify \
    && ln -s /opt/novnc/vnc.html /opt/novnc/index.html

# Instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar Chromium do Playwright
RUN playwright install chromium

# Copiar o código fonte
COPY . .

# Copiar configuração do supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Criar diretório para dados persistentes do Chromium
RUN mkdir -p /app/chrome_data

# Expor porta do noVNC
EXPOSE 6080

# Variável de ambiente para o display virtual
ENV DISPLAY=:99

# Supervisor gerencia todos os processos
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
