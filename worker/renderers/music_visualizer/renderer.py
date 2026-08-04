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
    "circle_radius": 170, "circle_max_scale": 1.55,
    "circle_border_color": "#ffffff", "circle_bg_color": "#00000099",
    "circle_glow_color": "auto", "circle_glow_intensity": 1.2,
    "circle_border_width": 5,
    # Movimento flutuante do círculo (fração do raio)
    "circle_float_amount": 0.07,   # deriva contínua ~7% do raio
    "circle_push_amount": 0.15,    # impulso na batida ~15% do raio
    "circle_shadow": True,         # sombra projetada (descola do fundo)
    "logo_text": "♫", "logo_font_size": 80, "logo_font_color": "#ffffff",
    # Ondas
    "waves_enabled": True, "wave_rings": 4,
    "wave_color": "auto", "wave_opacity_max": 0.8,
    # Espectro — 512 barras cobrindo 360°, com boost na batida
    "spectrum_enabled": True, "spectrum_bars": 512,
    "spectrum_color": "auto", "spectrum_opacity": 0.85,
    "spectrum_radius_offset": 20, "spectrum_max_height": 210,
    "spectrum_fill": 0.82,         # 82% do slot angular (gap fino entre barras)
    "spectrum_beat_boost": 0.55,   # quanto as barras sobem extra na batida
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
    # ── Novos sistemas (v2 — Animation Engine) ──
    "style_preset": "default",
    "postfx_quality": "auto",
    "camera_enabled": True,
    "scene_director_enabled": True,
    "idle_motion_enabled": True,
    "beat_variation_enabled": True,
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
        window = np.hanning(n_fft)

        # Índices de banda em escala LOGARÍTMICA (percepção humana de frequência).
        # Isso espalha os graves em mais barras e comprime os agudos, que é como
        # os visualizers profissionais distribuem o espectro.
        nyq_bins = n_fft // 2
        f_min_bin = max(1, int(20 / (sr / n_fft)))      # ~20 Hz
        f_max_bin = min(nyq_bins - 1, int(16000 / (sr / n_fft)))  # ~16 kHz
        log_edges = np.logspace(
            np.log10(f_min_bin), np.log10(f_max_bin), N_BANDS + 1
        ).astype(int)

        # ── Passo 1: calcular todos os espectros brutos (sem normalizar) ──
        raw_spectra = np.zeros((total_frames, N_BANDS), dtype=float)
        for i in range(total_frames):
            chunk = y[i * hop: i * hop + n_fft]
            if len(chunk) < n_fft:
                chunk = np.pad(chunk, (0, n_fft - len(chunk)))
            fft_mag = np.abs(np.fft.rfft(chunk * window))[:nyq_bins]
            for b in range(N_BANDS):
                lo, hi = log_edges[b], max(log_edges[b] + 1, log_edges[b + 1])
                raw_spectra[i, b] = fft_mag[lo:hi].max() if hi <= nyq_bins else 0.0

        # ── Passo 2: normalização GLOBAL (preserva a dinâmica entre frames) ──
        # Usa percentil 99 em vez do máximo absoluto para não ser dominado por
        # um único transiente extremo.
        global_ref = np.percentile(raw_spectra, 99.0)
        if global_ref <= 0:
            global_ref = raw_spectra.max() or 1.0

        # Compressão logarítmica (dB-like) — resposta visual natural
        norm = raw_spectra / global_ref
        norm = np.log1p(norm * 9.0) / np.log(10.0)   # log scale 0..~1
        norm = np.clip(norm * sensitivity, 0.0, 1.0)

        spectra = [row.tolist() for row in norm]

        # ── Passo 3: energia por banda (calculado aqui para payload leve) ──
        def band_avg(arr, lo_frac, hi_frac):
            lo = int(lo_frac * N_BANDS)
            hi = max(lo + 1, int(hi_frac * N_BANDS))
            return arr[:, lo:hi].mean(axis=1)

        bass = band_avg(norm, 0.00, 0.10)
        mid = band_avg(norm, 0.10, 0.42)
        high = band_avg(norm, 0.42, 0.78)
        presence = band_avg(norm, 0.78, 1.00)

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

        # ── Passo 4: Scene Detection ────────────────────────
        scenes = self._detect_scenes(rms, bass, mid, total_frames, fps)

        return {
            "rms": rms.tolist(),
            "spectra": spectra,
            "bass": bass.tolist(),
            "mid": mid.tolist(),
            "high": high.tolist(),
            "presence": presence.tolist(),
            "beats": beats.tolist(),
            "beat_strength": beat_strength.tolist(),
            "scenes": scenes,
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
    def _detect_scenes(rms, bass, mid, total_frames: int, fps: int) -> list:
        """Detecta seções da música baseado no envelope de energia.

        Usa janela móvel de 5s sobre energia combinada (rms+bass+mid).
        Classifica frames por percentil em intro/verse/buildup/drop/chorus/outro.
        Fallback temporal se detecção falhar.
        """
        import numpy as np

        if total_frames < fps * 10:  # música muito curta → fallback
            return _scene_fallback(total_frames)

        # Energia combinada com peso maior em bass (mais indicativo de seção)
        combined = (np.array(rms) + np.array(bass) * 1.5 + np.array(mid) * 0.5) / 3.0
        win = max(1, int(fps * 5))  # janela de 5s
        kernel = np.ones(win) / win
        envelope = np.convolve(combined, kernel, mode="same")
        env_max = envelope.max() or 1.0
        envelope = envelope / env_max

        # Percentis para classificação
        p30 = float(np.percentile(envelope, 30))
        p55 = float(np.percentile(envelope, 55))
        p78 = float(np.percentile(envelope, 78))
        p92 = float(np.percentile(envelope, 92))

        def classify(val):
            if val < p30:
                return "intro"
            elif val < p55:
                return "verse"
            elif val < p78:
                return "buildup"
            elif val < p92:
                return "chorus"
            else:
                return "drop"

        # Segmentar em blocos de ~2s
        block = max(1, int(fps * 2))
        raw_segments = []
        for start in range(0, total_frames, block):
            end = min(start + block, total_frames)
            avg = float(envelope[start:end].mean())
            raw_segments.append({"start": start, "end": end,
                                 "type": classify(avg), "intensity": avg})

        # Mesclar blocos consecutivos de mesmo tipo
        scenes = [dict(raw_segments[0])]
        for seg in raw_segments[1:]:
            if seg["type"] == scenes[-1]["type"]:
                scenes[-1]["end"] = seg["end"]
                scenes[-1]["intensity"] = max(scenes[-1]["intensity"],
                                              seg["intensity"])
            else:
                scenes.append(dict(seg))

        # Forçar último segmento como "outro" se >= 8% do total
        outro_min = int(total_frames * 0.08)
        if scenes and scenes[-1]["end"] - scenes[-1]["start"] >= outro_min:
            scenes[-1]["type"] = "outro"

        # Forçar primeiro segmento como "intro" se energia baixa
        if scenes and scenes[0]["intensity"] < p55:
            scenes[0]["type"] = "intro"

        return scenes if len(scenes) >= 2 else _scene_fallback(total_frames)

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

    @staticmethod
    def _gpu_present() -> bool:
        """Detecta acesso a GPU NVIDIA/AMD/Intel ou ambiente Windows.

        No Windows (sys.platform == 'win32' / os.name == 'nt'), a GPU nativa
        está sempre disponível via ANGLE (DirectX 11 / OpenGL).
        No Linux/Docker, checa dispositivos NVIDIA ou WSL2 /dev/dxg.
        """
        import sys
        if sys.platform == "win32" or os.name == "nt":
            return True
        if Path("/dev/nvidiactl").exists() or Path("/proc/driver/nvidia/version").exists():
            return True
        if Path("/dev/dxg").exists():   # WSL2 GPU passthrough
            return True
        try:
            r = subprocess.run(["nvidia-smi", "-L"],
                               capture_output=True, text=True, timeout=15)
            return r.returncode == 0 and "GPU" in r.stdout
        except Exception:
            return False

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

        # ── Montar frame data (payload leve: bandas pré-calculadas) ──
        rms = audio_data["rms"]
        spectra = audio_data["spectra"]
        beats = audio_data["beats"]
        bstr = audio_data["beat_strength"]
        bass = audio_data["bass"]
        mid = audio_data["mid"]
        high = audio_data["high"]
        pres = audio_data["presence"]

        # Payload SEM espectro — usado apenas para fast-forward de estado
        light_frames = [
            {
                "frameIndex": i, "totalFrames": total,
                "rms": float(rms[i]),
                "bass": float(bass[i]), "mid": float(mid[i]),
                "high": float(high[i]), "presence": float(pres[i]),
                "isBeat": bool(beats[i]), "beatStrength": float(bstr[i]),
                "progress": i / max(1, total - 1),
            }
            for i in range(total)
        ]

        # ── Definir paralelismo ──
        n_workers = int(cfg.get("render_workers", 0)) or min(
            6, max(1, (os.cpu_count() or 4) // 2)
        )
        n_workers = max(1, min(n_workers, 8))
        chunk = math.ceil(total / n_workers)
        ranges = [
            (s, min(s + chunk, total))
            for s in range(0, total, chunk)
        ]
        logger.info(
            f"Render: {total} frames em {len(ranges)} páginas paralelas "
            f"({chunk} frames/página)"
        )

        import sys
        headless = True
        win = sys.platform == "win32" or os.name == "nt"
        display = os.environ.get("DISPLAY")
        # WSL2 (Docker Desktop): GPU via Mesa d3d12 + libs DirectX do host.
        wsl_gpu = (Path("/dev/dxg").exists()
                   and Path("/usr/lib/wsl/lib/libd3d12.so").exists())

        if win:
            # Windows nativo: ANGLE sobre Direct3D 11 usa a GPU direto.
            gl_flags = [
                "--enable-gpu", "--ignore-gpu-blocklist",
                "--enable-gpu-rasterization", "--enable-zero-copy",
                "--use-gl=angle", "--use-angle=d3d11",
            ]
            backend = "GPU (ANGLE/D3D11)"
        elif wsl_gpu and display:
            # WSL2: Chromium PRECISA rodar headful (sob Xvfb) para usar a GPU;
            # em headless o ANGLE cai no SwiftShader (CPU). O driver Mesa d3d12
            # fala com a RTX via /dev/dxg usando as libs de /usr/lib/wsl/lib.
            os.environ.setdefault("GALLIUM_DRIVER", "d3d12")
            os.environ.setdefault("MESA_LOADER_DRIVER_OVERRIDE", "d3d12")
            if "/usr/lib/wsl/lib" not in os.environ.get("LD_LIBRARY_PATH", ""):
                os.environ["LD_LIBRARY_PATH"] = (
                    "/usr/lib/wsl/lib:" + os.environ.get("LD_LIBRARY_PATH", "")
                )
            headless = False
            gl_flags = [
                "--ignore-gpu-blocklist", "--enable-gpu-rasterization",
                "--use-gl=angle", "--use-angle=gl",
            ]
            backend = "GPU (Mesa d3d12 / WSL2)"
        else:
            # Linux sem GPU acessível → SwiftShader (CPU).
            use_gpu = self._gpu_present()
            gl_flags = [
                "--ignore-gpu-blocklist",
                "--use-gl=egl" if use_gpu else "--use-gl=swiftshader",
            ]
            backend = "CPU (SwiftShader)"
        logger.info(f"WebGL backend: {backend} | headless={headless}")

        done_counter = {"n": 0}

        init_payload = {
            "bgImage": bg_b64,
            "logoImage": logo_b64,
            "cfg": cfg,
            "title": title,
            "totalFrames": total,
            "scenes": audio_data.get("scenes", []),
        }

        async def render_chunk(ctx, start: int, end: int):
            """Renderiza [start, end) numa página própria.

            Faz fast-forward do estado de animação até `start` (1 round-trip),
            depois desenha e captura cada frame do seu intervalo.
            """
            page = await ctx.new_page()
            errors: list[str] = []
            page.on("console",
                    lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))

            await page.goto(f"file://{html_path}")
            await page.wait_for_load_state("domcontentloaded")

            if not await page.evaluate(
                "!!document.getElementById('c').getContext('webgl2')"
            ):
                raise RuntimeError("WebGL2 indisponível no Chromium headless.")

            # Log do backend GL real (só na 1ª página) — GPU vs SwiftShader
            if start == 0:
                try:
                    info = await page.evaluate("() => window.getGLInfo()")
                    is_sw = "swiftshader" in str(info.get("renderer", "")).lower() \
                        or "llvmpipe" in str(info.get("renderer", "")).lower()
                    logger.info(
                        f"WebGL RENDERER: {info.get('renderer')} | "
                        f"VENDOR: {info.get('vendor')} | quality={info.get('quality')} | "
                        f"{'⚠️ SOFTWARE (sem GPU)' if is_sw else '✅ GPU acelerada'}"
                    )
                except Exception as e:
                    logger.warning(f"Não foi possível obter GL info: {e}")

            await page.evaluate("(p) => window.initVisualizer(p)", init_payload)

            # Fast-forward: avança o estado sem desenhar (barato)
            if start > 0:
                await page.evaluate(
                    "([frames, target]) => window.fastForwardTo(frames, target)",
                    [light_frames[:start], start],
                )

            for i in range(start, end):
                fd = dict(light_frames[i])
                fd["spectrum"] = spectra[i]   # espectro só no frame desenhado
                await page.evaluate("(fd) => window.renderFrame(fd)", fd)
                await page.screenshot(
                    path=str(frames_dir / f"frame_{i:06d}.jpg"),
                    type="jpeg", quality=88, animations="disabled",
                )
                done_counter["n"] += 1
                n = done_counter["n"]
                if n % 25 == 0:
                    progress_fn(n / total, f"Frame {n}/{total}")
                    if errors:
                        logger.warning(f"JS errors: {errors[-2:]}")

            await page.close()

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--enable-webgl", "--enable-webgl2",
                    "--enable-accelerated-2d-canvas",
                    "--no-first-run",
                    "--disable-extensions", "--disable-background-networking",
                    "--allow-file-access-from-files",
                    "--disable-web-security",
                    *gl_flags,
                ],
            )
            ctx = await browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=1.0,
            )
            try:
                await asyncio.gather(*(render_chunk(ctx, s, e) for s, e in ranges))
            finally:
                await browser.close()

    # ──────────────────────────────────────────────────────
    #  Encode final
    # ──────────────────────────────────────────────────────

    @staticmethod
    def _nvenc_available() -> bool:
        """Testa se o encoder NVENC realmente funciona (driver + GPU presentes).

        Usa 320x240 porque o NVENC rejeita dimensões muito pequenas.
        """
        try:
            r = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error",
                 "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2",
                 "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True, text=True, timeout=40,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _encode(self, frames_dir: Path, audio_path: Path,
                output_path: Path, fps: int, duration: float):
        """Encoda os frames + áudio. Usa NVENC (GPU) se disponível, senão libx264."""
        base = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.jpg"),
            "-i", str(audio_path),
        ]
        tail = [
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            "-shortest", "-movflags", "+faststart",
            str(output_path),
        ]
        timeout = max(1800, int(duration * 12))

        if self._nvenc_available():
            logger.info("Encode: usando GPU (h264_nvenc)")
            vcodec = ["-c:v", "h264_nvenc", "-preset", "p4",
                      "-rc", "vbr", "-cq", "20", "-b:v", "0"]
            r = subprocess.run(base + vcodec + tail,
                               capture_output=True, text=True, timeout=timeout)
            if r.returncode == 0:
                return
            logger.warning(f"NVENC falhou, caindo para CPU: {r.stderr[-300:]}")

        logger.info("Encode: usando CPU (libx264)")
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        r = subprocess.run(base + vcodec + tail,
                           capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg falhou: {r.stderr[-600:]}")


def _scene_fallback(total_frames: int) -> list:
    """Progressão temporal quando a detecção de seções falhar."""
    T = total_frames
    return [
        {"start": 0,               "end": int(T * 0.08), "type": "intro",   "intensity": 0.3},
        {"start": int(T * 0.08),   "end": int(T * 0.30), "type": "verse",   "intensity": 0.5},
        {"start": int(T * 0.30),   "end": int(T * 0.45), "type": "buildup", "intensity": 0.7},
        {"start": int(T * 0.45),   "end": int(T * 0.65), "type": "drop",    "intensity": 1.0},
        {"start": int(T * 0.65),   "end": int(T * 0.88), "type": "chorus",  "intensity": 0.9},
        {"start": int(T * 0.88),   "end": T,              "type": "outro",   "intensity": 0.4},
    ]
