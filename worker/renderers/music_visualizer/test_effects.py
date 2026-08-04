"""Banco de testes do Music Visualizer — renderiza clipes curtos isolando
cada efeito individualmente, para inspeção visual antes de juntar tudo.

Como usar (dentro do container do worker):
    docker exec -it fabrica-worker python renderers/music_visualizer/test_effects.py

Opções:
    --audio   caminho do áudio (default: pega um .wav de /app/tts3_audio)
    --dur     duração em segundos de cada clipe de teste (default: 6)
    --res     resolução WxH (default: 854x480 — rápido)
    --fps     frames por segundo (default: 24)
    --effects lista separada por vírgula. Cada item vira um vídeo isolado.
              módulos válidos: bg, particles, halo, waves, spectrum, circle,
              lens, hud. Use 'full' para tudo junto e 'bg+spectrum' p/ combos.
    --out     pasta de saída (default: /app/mv_tests → visível no host em worker/mv_tests)

Os vídeos saem em <out>/<nome>.mp4. O log mostra o RENDERER WebGL (GPU real).
"""
from __future__ import annotations

import argparse
import glob
import logging
import shutil
import subprocess
import sys
from pathlib import Path

# Permite rodar tanto de /app quanto de dentro do pacote
sys.path.insert(0, "/app")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from renderers.music_visualizer.renderer import MusicVisualizerRenderer  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("MVTest")

# Efeitos isolados por padrão (cada um vira um vídeo)
DEFAULT_EFFECTS = [
    "full",
    "bg",
    "spectrum",
    "circle",
    "waves",
    "particles",
    "halo",
    "lens",
    "hud",
    "bg+spectrum+circle",
]


def _pick_audio() -> Path:
    """Escolhe um áudio de teste razoável (mais longo primeiro)."""
    candidates = sorted(
        glob.glob("/app/tts3_audio/**/*.wav", recursive=True)
        + glob.glob("/app/tts3_audio/*.wav"),
        key=lambda p: Path(p).stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise SystemExit("Nenhum .wav encontrado em /app/tts3_audio. Passe --audio.")
    return Path(candidates[0])


def _make_bg(path: Path, w: int, h: int):
    """Gera uma imagem de fundo colorida via ffmpeg (gradiente)."""
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"gradients=s={w}x{h}:c0=0x0b1e4d:c1=0x00d4ff:c2=0xff2e97:x0=0:y0=0:x1={w}:y1={h}:d=1",
        "-frames:v", "1", str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not path.exists():
        # fallback: cor sólida
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
             "-i", f"color=c=0x102040:s={w}x{h}", "-frames:v", "1", str(path)],
            capture_output=True,
        )


def _prep_audio(src: Path, dst: Path, dur: float):
    """Prepara o áudio do teste. dur<=0 usa o áudio inteiro; senão corta."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    if dur and dur > 0:
        cmd += ["-t", str(dur)]
    cmd += ["-i", str(src), "-ac", "1", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"Falha ao preparar áudio: {r.stderr[-300:]}")


def run(effects, audio, dur, w, h, fps, out_dir, bg=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    renderer = MusicVisualizerRenderer()
    bg_ext = bg.suffix.lower() if bg else ".png"

    for name in effects:
        work = Path(f"/tmp/mvtest_{name.replace('+','_')}")
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)

        if bg:
            shutil.copy(bg, work / f"bg_image{bg_ext}")
        else:
            _make_bg(work / "bg_image.png", w, h)
        _prep_audio(audio, work / "audio.wav", dur)

        solo = None if name == "full" else name.split("+")
        job_data = {
            "title": f"TEST · {name}",
            "files": {"bg_image_ext": bg_ext, "audio_ext": ".wav"},
            "visualizer": {
                "width": w, "height": h, "fps": fps,
                "debug_solo": solo,
                # 1 página só (fast-forward previsível nos testes curtos)
                "render_workers": 1,
            },
        }

        log.info(f"───── Renderizando efeito isolado: '{name}' ({w}x{h}@{fps}, {dur}s)")
        try:
            output = renderer.render(job_data, work)
            dst = out_dir / f"{name.replace('+','_')}.mp4"
            shutil.copy(output, dst)
            log.info(f"✅ '{name}' → {dst} ({dst.stat().st_size/1024/1024:.1f}MB)")
        except Exception as e:
            log.exception(f"❌ Falha no efeito '{name}': {e}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    log.info(f"Concluído. Vídeos em: {out_dir}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=None)
    ap.add_argument("--bg", default=None, help="imagem de fundo (default: gera gradiente)")
    ap.add_argument("--dur", type=float, default=6.0, help="segundos por clipe; 0 = áudio inteiro")
    ap.add_argument("--res", default="854x480")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--effects", default=",".join(DEFAULT_EFFECTS))
    ap.add_argument("--out", default="/app/mv_tests")
    args = ap.parse_args()

    audio = Path(args.audio) if args.audio else _pick_audio()
    bg = Path(args.bg) if args.bg else None
    w, h = (int(x) for x in args.res.lower().split("x"))
    effects = [e.strip() for e in args.effects.split(",") if e.strip()]
    log.info(f"Áudio de teste: {audio} | fundo: {bg or '(gradiente gerado)'} | dur: {args.dur or 'inteiro'}")
    run(effects, audio, args.dur, w, h, args.fps, args.out, bg=bg)


if __name__ == "__main__":
    main()
