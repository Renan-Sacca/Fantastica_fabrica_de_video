"""Gerador de card estilo Reddit para intro/thumbnail de vídeos.

Usa Pillow para desenhar um cartão parecido com um post do Reddit:
- Avatar circular (snoo estilizado)
- Nome de usuário ("Anônimo") + badges
- Título em negrito com quebra de linha automática
- Cantos arredondados, tema claro ou escuro, cor de destaque configurável
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("RedditCard")

# Caminhos de fontes comuns em containers Debian/Ubuntu
FONT_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
FONT_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

CANVAS_W = 1080
CANVAS_H = 1920


def _load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    # Fallback para fonte padrão do Pillow (bitmap, sem tamanho ideal)
    logger.warning("Nenhuma fonte TrueType encontrada, usando fonte padrão.")
    return ImageFont.load_default()


def _hex_to_rgb(color: str) -> Tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    try:
        return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore
    except Exception:
        return (0, 0, 0)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Quebra o texto em várias linhas respeitando a largura máxima."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        w = draw.textlength(test, font=font)
        if w <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _draw_snoo(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, accent: Tuple[int, int, int]):
    """Desenha um avatar circular com um 'snoo' (mascote do Reddit) simplificado."""
    # Círculo de fundo com a cor de destaque
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)

    white = (255, 255, 255)
    # Corpo/cabeça do snoo (elipse branca central)
    head_r = int(r * 0.42)
    draw.ellipse(
        [cx - head_r, cy - int(head_r * 0.2), cx + head_r, cy + int(head_r * 1.4)],
        fill=white,
    )
    # Cabeça (círculo)
    draw.ellipse(
        [cx - int(head_r * 0.75), cy - int(head_r * 0.9), cx + int(head_r * 0.75), cy + int(head_r * 0.6)],
        fill=white,
    )
    # Antena
    ant_x = cx + int(head_r * 0.5)
    draw.line([(cx, cy - int(head_r * 0.6)), (ant_x, cy - int(head_r * 1.3))], fill=white, width=max(2, r // 20))
    draw.ellipse(
        [ant_x - int(r * 0.08), cy - int(head_r * 1.3) - int(r * 0.08),
         ant_x + int(r * 0.08), cy - int(head_r * 1.3) + int(r * 0.08)],
        fill=white,
    )
    # Olhos (com a cor de destaque)
    eye_r = max(2, int(head_r * 0.16))
    ey = cy - int(head_r * 0.15)
    draw.ellipse([cx - int(head_r * 0.35) - eye_r, ey - eye_r,
                  cx - int(head_r * 0.35) + eye_r, ey + eye_r], fill=accent)
    draw.ellipse([cx + int(head_r * 0.35) - eye_r, ey - eye_r,
                  cx + int(head_r * 0.35) + eye_r, ey + eye_r], fill=accent)


def generate_reddit_card(
    output_path: Path,
    title: str,
    username: str = "Anônimo",
    theme: str = "light",
    accent_color: str = "#FF4500",
    card_width: int = 920,
) -> Path:
    """Gera um PNG transparente (1080x1920) com um card estilo Reddit centralizado.

    Args:
        output_path: caminho do PNG de saída.
        title: texto do título do post.
        username: nome exibido no cabeçalho.
        theme: 'light' (card branco) ou 'dark' (card escuro).
        accent_color: cor de destaque (borda, avatar, badges) em hex.
        card_width: largura do card em pixels.
    """
    accent = _hex_to_rgb(accent_color)

    if theme == "dark":
        card_bg = (26, 26, 27, 255)      # #1a1a1b
        text_color = (215, 218, 220, 255)
        muted_color = (129, 131, 132, 255)
    else:
        card_bg = (255, 255, 255, 255)
        text_color = (26, 26, 27, 255)
        muted_color = (120, 124, 126, 255)

    canvas = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Fontes
    font_title = _load_font(FONT_BOLD_CANDIDATES, 52)
    font_user = _load_font(FONT_BOLD_CANDIDATES, 34)
    font_badge = _load_font(FONT_REGULAR_CANDIDATES, 24)

    # Layout do card
    pad = 48
    card_x = (CANVAS_W - card_width) // 2
    inner_w = card_width - pad * 2

    # Cabeçalho: avatar + username
    avatar_r = 38
    header_h = avatar_r * 2

    # Título (quebra de linha)
    title_lines = _wrap_text(draw, title, font_title, inner_w)
    line_h = int(font_title.size * 1.28)
    title_block_h = line_h * len(title_lines)

    # Altura total do card
    gap_header_title = 34
    card_h = pad + header_h + gap_header_title + title_block_h + pad

    # Posição vertical: centralizado, levemente acima do meio
    card_y = (CANVAS_H - card_h) // 2 - 60

    # Sombra suave
    shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        [card_x + 6, card_y + 12, card_x + card_width + 6, card_y + card_h + 12],
        radius=34, fill=(0, 0, 0, 90),
    )
    shadow = shadow.filter(_blur(18))
    canvas = Image.alpha_composite(canvas, shadow)
    draw = ImageDraw.Draw(canvas)

    # Borda de destaque (glow atrás do card)
    draw.rounded_rectangle(
        [card_x - 5, card_y - 5, card_x + card_width + 5, card_y + card_h + 5],
        radius=38, fill=(*accent, 255),
    )

    # Card principal
    draw.rounded_rectangle(
        [card_x, card_y, card_x + card_width, card_y + card_h],
        radius=34, fill=card_bg,
    )

    # Avatar
    ax = card_x + pad + avatar_r
    ay = card_y + pad + avatar_r
    _draw_snoo(draw, ax, ay, avatar_r, accent)

    # Username
    ux = ax + avatar_r + 22
    uy = ay - font_user.size // 2 - 4
    draw.text((ux, uy), username, font=font_user, fill=text_color)

    # Badges (pequenos ícones após o nome)
    uname_w = draw.textlength(username, font=font_user)
    bx = ux + uname_w + 18
    by = ay - 14
    badge_specs = [("🏆", (255, 180, 0)), ("⭐", (255, 210, 60)), ("🔥", (255, 90, 30))]
    for emoji, bcolor in badge_specs:
        draw.ellipse([bx, by, bx + 28, by + 28], fill=(*bcolor, 60))
        draw.ellipse([bx + 6, by + 6, bx + 22, by + 22], fill=bcolor)
        bx += 38

    # Título
    ty = ay + avatar_r + gap_header_title
    tx = card_x + pad
    for line in title_lines:
        draw.text((tx, ty), line, font=font_title, fill=text_color)
        ty += line_h

    canvas.save(output_path, "PNG")
    logger.info(f"Card Reddit gerado: {output_path} ({len(title_lines)} linhas)")
    return output_path


def _blur(radius: int):
    """Retorna o filtro de blur gaussiano do Pillow."""
    from PIL import ImageFilter
    return ImageFilter.GaussianBlur(radius)
