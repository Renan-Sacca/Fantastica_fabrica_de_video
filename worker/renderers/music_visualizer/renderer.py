"""Renderer do tipo 'music_visualizer' — motor WebGL via Playwright + PixiJS.

Fluxo:
1. Analisa o áudio com librosa/numpy: RMS, FFT (espectro), beats, energia
2. Exporta os dados de áudio como JSON (frameData por frame)
3. Abre o visualizer HTML/WebGL com Playwright headless
4. Chama renderFrame(data) para cada frame e captura screenshot
5. Encoda os frames em MP4 com ffmpeg + áudio original

O HTML usa PixiJS v8 (WebGL2) com filtros de pós-processamento:
- Bloom (glow real), ColorMatrix, CRT (chromatic aberration), Blur
- Espectro de frequências (barras/ondas) via OffscreenCanvas
- Partículas com física, profundidade e motion blur
- Ken Burns, parallax, camera shake, easing spring
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import math
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from renderers.base import BaseRenderer

logger = logging.getLogger("MusicVisualizerRenderer")

# ─── Defaults ────────────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "width": 1920, "height": 1080, "fps": 30,
    # Círculo
    "circle_radius": 200, "circle_max_scale": 1.55,
    "circle_border_color": "#ffffff", "circle_bg_color": "#00000099",
    "circle_glow_color": "auto", "circle_glow_intensity": 1.2,
    "circle_border_width": 5,
    "logo_text": "♫", "logo_font_size": 80, "logo_font_color": "#ffffff",
    # Ondas
    "waves_enabled": True, "wave_rings": 4,
    "wave_color": "auto", "wave_opacity_max": 0.8,
    # Espectro — 512 barras, raio maior, mais alto
    "spectrum_enabled": True, "spectrum_bars": 512,
    "spectrum_color": "auto", "spectrum_opacity": 0.85,
    "spectrum_radius_offset": 20, "spectrum_max_height": 200,
    # Fundo
    "bg_zoom_speed": 0.04, "bg_zoom_max": 1.12,
    "bg_beat_shake": True, "bg_beat_shake_px": 7,
    "bg_brightness_boost": 0.30, "bg_blur_ambient": 0.0,
    "bg_parallax": True, "bg_rotation_speed": 0.3,
    "film_grain": 0.5,
    # Partículas — 4 camadas de profundidade
    "particles_enabled": True, "particle_count": 100,
    "particle_color": "auto", "particle_opacity_max": 0.65,
    "particle_size_min": 1.5, "particle_size_max": 5.0, "particle_speed": 1.0,
    # Pós-processamento
    "chromatic_aberration": 0.0008,
    "vignette_enabled": True, "vignette_strength": 0.42,
    # Lens flare
    "lens_flare": True,
    # Barra de progresso
    "progress_bar_enabled": True, "progress_bar_color": "auto",
    "progress_bar_position": "bottom",
    # Título
    "show_title": True, "title_color": "#ffffff", "title_font_size": 32,
    "title_opacity": 0.85, "title_position": "bottom-center", "title_margin": 56,
    # Áudio
    "audio_sensitivity": 1.3, "beat_threshold": 0.50,
}


class MusicVisualizerRenderer(BaseRenderer):

    @property
    def video_type(self) -> str:
        return "music_visualizer"

    def render(
        self,
        job_data: dict,
        work_dir: Path,
        progress_callback: Optional[Callable] = None,
    ) -> Path:
        def _cb(status, pct, detail):
            if progress_callback:
                progress_callback(status=status, progress=pct, detail=detail)

        cfg = {**DEFAULTS, **job_data.get("visualizer", {})}
        _cb("rendering", 5, "Carregando arquivos...")

        # Localizar arquivos
        bg_ext = job_data.get("files", {}).get("bg_image_ext", ".jpg")
        bg_path = work_dir / f"bg_image{bg_ext}"
        if not bg_path.exists():
            for ext in [".png", ".jpg", ".jpeg", ".webp"]:
                p = work_dir / f"bg_image{ext}"
                if p.exists():
                    bg_path = p
                    break
        if not bg_path.exists():
            raise FileNotFoundError(f"Imagem de fundo não encontrada em {work_dir}")

        logo_ext = job_data.get("files", {}).get("logo_ext", "")
        logo_path = work_dir / f"logo{logo_ext}" if logo_ext else None
        if logo_path and not logo_path.exists():
            logo_path = None

        audio_ext = job_data.get("files", {}).get("audio_ext", ".mp3")
        audio_path = work_dir / f"audio{audio_ext}"
        if not audio_path.exists():
            raise FileNotFoundError(f"Áudio não encontrado em {work_dir}")

        title = job_data.get("title", "")

        _cb("rendering", 10, "Analisando áudio (FFT + beats)...")
        audio_data = self._analyze_audio(audio_path, cfg)
        duration = audio_data["duration"]
        total_frames = audio_data["total_frames"]
        logger.info(f"Áudio: {duration:.2f}s | {total_frames} frames | {audio_data['sr']}Hz")

        _cb("rendering", 18, "Preparando assets...")
        bg_b64 = self._file_to_b64(bg_path)
        logo_b64 = self._file_to_b64(logo_path) if logo_path else None

        _cb("rendering", 22, "Renderizando frames WebGL...")
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(exist_ok=True)

        asyncio.run(self._render_all_frames(
            bg_b64=bg_b64, logo_b64=logo_b64,
            audio_data=audio_data, frames_dir=frames_dir,
            cfg=cfg, title=title,
            progress_fn=lambda p, d: _cb("rendering", 22 + int(p * 62), d),
        ))

        _cb("composing", 86, "Encodando vídeo...")
        output_path = work_dir / "output.mp4"
        self._encode(frames_dir, audio_path, output_path, cfg["fps"], duration)

        _cb("composing", 98, "Vídeo pronto!")
        logger.info(f"Output: {output_path} ({output_path.stat().st_size/1024/1024:.1f}MB)")
        return output_path

    # ──────────────────────────────────────────────────────
    #  Análise de Áudio
    # ──────────────────────────────────────────────────────

    def _analyze_audio(self, audio_path: Path, cfg: dict) -> dict:
        import numpy as np

        try:
            import librosa
            y, sr = librosa.load(str(audio_path), sr=None, mono=True)
        except ImportError:
            y, sr = self._load_pcm_ffmpeg(audio_path)

        fps = int(cfg["fps"])
        duration = len(y) / sr
        total_frames = int(duration * fps)
        hop = max(1, int(sr / fps))
        sensitivity = float(cfg.get("audio_sensitivity", 1.3))

        # RMS por frame
        rms_arr = []
        for i in range(total_frames):
            chunk = y[i * hop: i * hop + hop]
            rms_arr.append(float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0)
        rms = np.array(rms_arr)
        rms_max = rms.max() or 1.0
        rms = np.clip(rms / rms_max * sensitivity, 0, 1)
        rms = self._smooth(rms, 3)

        # Espectro FFT por frame (512 bandas para spectrum visual)
        N_BANDS = int(cfg.get("spectrum_bars", 512))
        n_fft = 4096  # maior janela = melhor resolução de frequência
        spectra = []
        for i in range(total_frames):
            chunk = y[i * hop: i * hop + n_fft]
            if len(chunk) < n_fft:
                chunk = np.pad(chunk, (0, n_fft - len(chunk)))
            window = np.hanning(n_fft)
            fft_mag = np.abs(np.fft.rfft(chunk * window))[: n_fft // 2]
            # Reduzir para N_BANDS com compressão log
            bands = np.array_split(fft_mag[:min(len(fft_mag), N_BANDS * 4)], N_BANDS)
            band_vals = np.array([np.mean(b) for b in bands], dtype=float)
            band_max = band_vals.max() or 1.0
            band_vals = np.clip(band_vals / band_max * sensitivity, 0, 1)
            spectra.append(band_vals.tolist())

        # Beats: pico local acima do threshold
        beat_th = float(cfg["beat_threshold"]) * float(rms.mean()) * 4
        beats = np.zeros(total_frames, dtype=bool)
        for i in range(2, total_frames - 2):
            window_rms = rms[max(0, i - 3): i + 3]
            if rms[i] >= window_rms.max() and rms[i] > beat_th:
                beats[i] = True

        # Beat strength (decay exponencial após cada beat)
        beat_strength = np.zeros(total_frames)
        last = 0.0
        for i in range(total_frames):
            if beats[i]:
                last = 1.0
            beat_strength[i] = last
            last *= 0.82

        return {
            "rms": rms.tolist(),
            "spectra": spectra,
            "beats": beats.tolist(),
            "beat_strength": beat_strength.tolist(),
            "duration": duration,
            "total_frames": total_frames,
            "fps": fps,
            "sr": sr,
        }

    def _load_pcm_ffmpeg(self, audio_path: Path, sr: int = 22050):
        import numpy as np
        cmd = ["ffmpeg", "-y", "-i", str(audio_path),
               "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        raw = r.stdout
        n = len(raw) // 2
        samples = struct.unpack(f"{n}h", raw)
        return np.array(samples, dtype=float) / 32768.0, sr

    @staticmethod
    def _smooth(arr, w: int = 3):
        import numpy as np
        return np.convolve(arr, np.ones(w) / w, mode="same")

    @staticmethod
    def _file_to_b64(path: Path) -> str:
        data = path.read_bytes()
        ext = path.suffix.lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
                "png": "image/png", "webp": "image/webp",
                "gif": "image/gif"}.get(ext.lower(), "image/jpeg")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"

    # ──────────────────────────────────────────────────────
    #  Renderização assíncrona via Playwright
    # ──────────────────────────────────────────────────────

    async def _render_all_frames(
        self, bg_b64: str, logo_b64: Optional[str],
        audio_data: dict, frames_dir: Path,
        cfg: dict, title: str,
        progress_fn: Callable,
    ) -> None:
        from playwright.async_api import async_playwright

        html_path = Path(__file__).resolve().parent / "frontend" / "index.html"
        total = audio_data["total_frames"]
        w, h = int(cfg["width"]), int(cfg["height"])

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--enable-webgl", "--enable-webgl2",
                    "--ignore-gpu-blocklist",
                    "--use-gl=swiftshader",   # Software WebGL2 — funciona sem GPU
                    "--enable-accelerated-2d-canvas",
                    "--no-first-run", "--no-zygote",
                    "--disable-extensions", "--disable-background-networking",
                    "--allow-file-access-from-files",
                    "--disable-web-security",
                ],
            )
            ctx = await browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=1.0,
            )
            page = await ctx.new_page()

            # Capturar erros críticos do console
            console_errors = []
            page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: console_errors.append(str(e)))

            await page.goto(f"file://{html_path}")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(800)

            # Verificar se WebGL2 foi inicializado
            webgl_ok = await page.evaluate("!!document.getElementById('c').getContext('webgl2')")
            if not webgl_ok:
                raise RuntimeError("WebGL2 não disponível no Playwright headless. Verifique as flags do Chromium.")

            # Inicializar o visualizer
            init_payload = {
                "bgImage": bg_b64,
                "logoImage": logo_b64,
                "cfg": cfg,
                "title": title,
                "totalFrames": total,
            }
            await page.evaluate(
                "(payload) => window.initVisualizer(payload)",
                init_payload,
            )
            # initVisualizer é async — page.evaluate aguarda a Promise automaticamente
            # Aguardar um pouco extra para as texturas renderizarem
            await page.wait_for_timeout(500)

            # Renderizar frames
            rms = audio_data["rms"]
            spectra = audio_data["spectra"]
            beats = audio_data["beats"]
            beat_strength = audio_data["beat_strength"]

            for i in range(total):
                frame_data = {
                    "frameIndex": i,
                    "totalFrames": total,
                    "rms": float(rms[i]),
                    "spectrum": spectra[i],
                    "isBeat": bool(beats[i]),
                    "beatStrength": float(beat_strength[i]),
                    "progress": i / max(1, total - 1),
                }
                await page.evaluate("(fd) => window.renderFrame(fd)", frame_data)
                frame_path = str(frames_dir / f"frame_{i:06d}.jpg")
                await page.screenshot(
                    path=frame_path, type="jpeg", quality=88,
                    animations="disabled",
                )
                if i % 30 == 0:
                    progress_fn(i / total, f"Frame {i}/{total}")
                    if console_errors:
                        logger.warning(f"JS errors: {console_errors[-3:]}")

            await browser.close()

    # ──────────────────────────────────────────────────────
    #  Encode final
    # ──────────────────────────────────────────────────────

    def _encode(self, frames_dir: Path, audio_path: Path,
                output_path: Path, fps: int, duration: float):
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.jpg"),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "fast", "-crf", "17",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            "-shortest", "-movflags", "+faststart",
            str(output_path),
        ]
        timeout = max(1800, int(duration * 12))
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou: {r.stderr[-600:]}")
