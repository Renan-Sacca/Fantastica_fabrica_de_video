"""WhatsAppRenderer — implementação completa do BaseRenderer."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional

from renderers.base import BaseRenderer

logger = logging.getLogger(__name__)


class WhatsAppRenderer(BaseRenderer):
    """Renderiza vídeos no estilo WhatsApp usando Playwright + FFmpeg."""

    @property
    def video_type(self) -> str:
        return "whatsapp"

    def render(
        self,
        job_data: dict,
        work_dir: Path,
        progress_callback: Optional[Callable] = None,
    ) -> Path:
        """
        Renderiza o vídeo e retorna o path do .mp4 gerado.

        Args:
            job_data: Conteúdo do metadata.json (baixado do Drive)
            work_dir: Pasta local com todos os arquivos do job
            progress_callback: fn(status=None, progress=0, detail='')
        """
        from renderers.whatsapp.engine import render_video
        from renderers.whatsapp.models import (
            AnimationStyle,
            ConversationConfig,
            RenderJob,
            VideoFormat,
        )
        from renderers.whatsapp.parser import parse_conversation

        # ── Reconstruir config ──
        config = ConversationConfig(
            contact_name=job_data.get("contact_name", "Contato"),
            contact_status=job_data.get("contact_status", "online"),
            video_format=VideoFormat(job_data.get("video_format", "vertical")),
            fps=int(job_data.get("fps", 30)),
            speed=float(job_data.get("speed", 1.0)),
            reading_speed=float(job_data.get("reading_speed", 1.0)),
            scroll_speed=float(job_data.get("scroll_speed", 1.0)),
            animation_style=AnimationStyle(job_data.get("animation_style", "fade")),
        )

        # ── Parse conversa ──
        conv_file = work_dir / "conversa.txt"
        if not conv_file.exists():
            raise FileNotFoundError(f"conversa.txt não encontrada em {work_dir}")

        conv_text = conv_file.read_text(encoding="utf-8")
        messages = parse_conversation(conv_text, "conversa.txt")

        if not messages:
            raise ValueError("Nenhuma mensagem encontrada na conversa")

        # ── Corrigir caminhos de imagens ──
        for msg in messages:
            if msg.media_path:
                local_path = work_dir / msg.media_path
                if local_path.exists():
                    msg.media_path = str(local_path)
                else:
                    # Tentar apenas pelo nome do arquivo na pasta imagens/
                    filename = Path(msg.media_path).name
                    img_path = work_dir / "imagens" / filename
                    if img_path.exists():
                        msg.media_path = str(img_path)
                    else:
                        logger.warning(f"Imagem não encontrada: {msg.media_path}")
                        msg.media_path = None

        # ── Construir RenderJob ──
        job = RenderJob(
            job_id=job_data["job_id"],
            config=config,
            messages=messages,
            bg_color=job_data.get("bg_color") or None,
        )

        # Arquivos opcionais
        files = job_data.get("files", {})
        foto_ext = files.get("foto_perfil_ext", ".jpg")
        wp_ext = files.get("papel_parede_ext", ".jpg")
        music_ext = files.get("musica_ext", ".mp3")

        for filename in [f"foto_perfil{foto_ext}", "foto_perfil.jpg", "foto_perfil.png"]:
            p = work_dir / filename
            if p.exists():
                job.contact_photo_path = str(p)
                break

        for filename in [f"papel_parede{wp_ext}", "papel_parede.jpg", "papel_parede.png"]:
            p = work_dir / filename
            if p.exists():
                job.wallpaper_path = str(p)
                break

        for filename in [f"musica{music_ext}", "musica.mp3", "musica.ogg", "musica.wav"]:
            p = work_dir / filename
            if p.exists():
                job.background_music_path = str(p)
                break

        # ── Output path ──
        output_path = work_dir / "output.mp4"

        # ── Renderizar ──
        render_video(job, output_path, progress_callback)

        return output_path
