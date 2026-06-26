"""Baixa os pesos do OmniVoice de forma robusta (retry + verificação).

Resolve o erro 'SafetensorError: header too small', que ocorre quando um
arquivo .safetensors vem truncado (rate limit do HF / transferência xet).
"""
import os
import time
from pathlib import Path

# Evita downloads parciais do backend "xet" e do hf_transfer
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

from huggingface_hub import snapshot_download
from safetensors import safe_open

REPO = "k2-fsa/OmniVoice"


def _verify(path: str) -> list:
    """Retorna a lista de arquivos .safetensors corrompidos."""
    bad = []
    for f in Path(path).rglob("*.safetensors"):
        try:
            with safe_open(str(f), framework="pt", device="cpu"):
                pass
        except Exception as e:
            bad.append((str(f), repr(e)))
    return bad


def main() -> None:
    last_err = None
    for attempt in range(1, 6):
        try:
            force = attempt > 1  # se já tentou, força re-download limpo
            path = snapshot_download(REPO, max_workers=2, force_download=force)
            bad = _verify(path)
            if bad:
                print(f"[tentativa {attempt}] arquivos corrompidos: {bad}")
                last_err = bad
                time.sleep(5)
                continue
            print(f"Modelo OmniVoice baixado e verificado em: {path}")
            return
        except Exception as e:
            print(f"[tentativa {attempt}] falhou: {e}")
            last_err = e
            time.sleep(5)
    raise SystemExit(f"Falha ao baixar o modelo OmniVoice: {last_err}")


if __name__ == "__main__":
    main()
