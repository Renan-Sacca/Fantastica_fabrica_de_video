#!/usr/bin/env bash
# Entrypoint do worker.
#
# Sobe um display virtual (Xvfb) para que o Chromium possa rodar em modo
# "headful" — condição necessária para usar a GPU no WebGL (em headless o
# ANGLE cai no SwiftShader/CPU). Depois inicia o worker normalmente.
#
# Se a GPU não estiver disponível, o renderer detecta e faz fallback
# automático para SwiftShader; o Xvfb rodando não atrapalha nesse caso.
set -e

export DISPLAY="${DISPLAY:-:99}"
SCREEN="${XVFB_SCREEN:-1920x1080x24}"

# Inicia o Xvfb em background (se ainda não estiver rodando)
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  Xvfb "${DISPLAY}" -screen 0 "${SCREEN}" -ac +extension GLX +render -noreset \
    >/tmp/xvfb.log 2>&1 &
fi

# Aguarda o socket do X aparecer (máx ~6s)
disp_num="${DISPLAY#:}"
for _ in $(seq 1 20); do
  if [ -S "/tmp/.X11-unix/X${disp_num}" ]; then
    break
  fi
  sleep 0.3
done

echo "[entrypoint] DISPLAY=${DISPLAY} (Xvfb ${SCREEN}) — iniciando worker"
exec python main.py
