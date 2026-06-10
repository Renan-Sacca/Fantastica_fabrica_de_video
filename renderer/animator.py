"""
Módulo de animação e timeline.

Calcula o estado da conversa em qualquer instante de tempo,
incluindo scroll, opacidade de mensagens, indicador de digitação, etc.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from api.models import Message, MessageType


@dataclass
class MessageEvent:
    """Evento de uma mensagem na timeline."""
    index: int
    message: Message
    appear_time: float       # Quando a mensagem começa a aparecer (ms)
    fully_visible_time: float  # Quando está 100% visível (ms)
    typing_start: float      # Quando "digitando..." aparece (ms), -1 se não aplica
    typing_end: float        # Quando "digitando..." desaparece (ms)
    scroll_start: float      # Quando scroll para esta mensagem começa (ms)
    scroll_end: float        # Quando scroll para esta mensagem termina (ms)
    target_scroll_y: float   # Posição Y de scroll quando esta msg é foco


@dataclass
class FrameState:
    """Estado de um frame específico."""
    scroll_y: float = 0.0
    visible_messages: list[int] = field(default_factory=list)
    message_opacity: dict[int, float] = field(default_factory=dict)
    message_translate_y: dict[int, float] = field(default_factory=dict)
    show_typing: bool = False
    typing_sender: str = ""
    status_bar_time: str = "10:30"


def ease_in_out_cubic(t: float) -> float:
    """Easing cúbico suave - entrada e saída."""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def ease_out_quad(t: float) -> float:
    """Easing quadrático - desaceleração natural."""
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_out_cubic(t: float) -> float:
    """Easing cúbico - desaceleração mais forte."""
    t = max(0.0, min(1.0, t))
    return 1.0 - pow(1.0 - t, 3)


def humanize(value: float, variation: float = 0.20, rng: Optional[random.Random] = None) -> float:
    """Adiciona variação humana a um valor."""
    r = rng or random
    factor = 1.0 + r.uniform(-variation, variation)
    return value * factor


class Timeline:
    """
    Calcula a timeline completa da conversa e o estado de qualquer frame.

    A timeline define quando cada mensagem aparece, quando há scroll,
    pausas de leitura, indicadores de digitação, etc.
    """

    def __init__(
        self,
        messages: list[Message],
        fps: int = 30,
        speed: float = 1.0,
        reading_speed: float = 1.0,
        scroll_speed: float = 1.0,
        animation_style: str = "fade",
        seed: Optional[int] = None,
        message_height: float = 60.0,
        viewport_height: float = 1920.0,
        header_height: float = 80.0,
        input_bar_height: float = 60.0,
    ):
        self.messages = messages
        self.fps = fps
        self.speed = speed
        self.reading_speed = reading_speed
        self.scroll_speed = scroll_speed
        self.animation_style = animation_style
        self.rng = random.Random(seed)
        self.message_height = message_height
        self.viewport_height = viewport_height
        self.header_height = header_height
        self.input_bar_height = input_bar_height
        self.usable_height = viewport_height - header_height - input_bar_height

        self.events: list[MessageEvent] = []
        self.total_duration_ms: float = 0
        self.total_frames: int = 0

        self._build_timeline()

    def _get_message_delay(self, msg: Message) -> float:
        """Calcula delay base antes de uma mensagem (ms)."""
        if msg.type == MessageType.DATE_SEPARATOR:
            return humanize(300, rng=self.rng) / self.speed

        text_len = len(msg.text or "")

        if msg.type == MessageType.IMAGE:
            base = humanize(2000, rng=self.rng)
        elif msg.type == MessageType.AUDIO:
            base = humanize(1800, rng=self.rng)
        elif msg.type == MessageType.EMOJI:
            base = humanize(600, rng=self.rng)
        elif text_len > 100:
            base = humanize(2200, rng=self.rng)
        elif text_len > 50:
            base = humanize(1600, rng=self.rng)
        else:
            base = humanize(1000, rng=self.rng)

        return base / self.speed

    def _get_reading_pause(self, msg: Message) -> float:
        """Tempo de pausa para 'ler' a mensagem (ms)."""
        if msg.type == MessageType.DATE_SEPARATOR:
            return humanize(200, rng=self.rng) / self.reading_speed

        text_len = len(msg.text or "")

        if msg.type == MessageType.IMAGE:
            base = humanize(2500, rng=self.rng)
        elif msg.type == MessageType.AUDIO:
            base = humanize(2000, rng=self.rng)
        elif text_len > 100:
            base = humanize(2000, rng=self.rng)
        elif text_len > 50:
            base = humanize(1500, rng=self.rng)
        else:
            base = humanize(800, rng=self.rng)

        return base / self.reading_speed

    def _get_animation_duration(self) -> float:
        """Duração da animação de aparecimento (ms)."""
        return humanize(350, variation=0.1, rng=self.rng)

    def _get_typing_duration(self, msg: Message) -> float:
        """Duração do indicador 'digitando...' (ms)."""
        text_len = len(msg.text or "")
        base = min(500 + text_len * 15, 2000)
        return humanize(base, rng=self.rng) / self.speed

    def _get_scroll_duration(self) -> float:
        """Duração do scroll suave (ms)."""
        return humanize(450, rng=self.rng) / self.scroll_speed

    def _build_timeline(self) -> None:
        """Constrói a timeline completa de eventos."""
        current_time = 500.0  # Começa com uma pausa inicial
        accumulated_height = 0.0

        for i, msg in enumerate(self.messages):
            # Delay antes desta mensagem
            delay = self._get_message_delay(msg)
            current_time += delay

            # Indicador de digitação (só para mensagens recebidas de texto)
            typing_start = -1.0
            typing_end = -1.0
            if (
                msg.sender != "me"
                and msg.type == MessageType.TEXT
                and self.animation_style == "typing"
            ):
                typing_dur = self._get_typing_duration(msg)
                typing_start = current_time
                typing_end = current_time + typing_dur
                current_time = typing_end

            # Animação de aparecimento
            anim_dur = self._get_animation_duration()
            appear_time = current_time
            fully_visible_time = current_time + anim_dur

            # Calcular scroll necessário
            # Estimar altura acumulada das mensagens
            msg_h = self._estimate_msg_height(msg)
            accumulated_height += msg_h

            # Scroll necessário para manter a mensagem visível
            target_scroll = max(0, accumulated_height - self.usable_height + 100)

            scroll_dur = self._get_scroll_duration()
            scroll_start = appear_time
            scroll_end = appear_time + scroll_dur

            event = MessageEvent(
                index=i,
                message=msg,
                appear_time=appear_time,
                fully_visible_time=fully_visible_time,
                typing_start=typing_start,
                typing_end=typing_end,
                scroll_start=scroll_start,
                scroll_end=scroll_end,
                target_scroll_y=target_scroll,
            )
            self.events.append(event)

            # Avançar tempo com pausa de leitura
            reading_pause = self._get_reading_pause(msg)
            current_time = fully_visible_time + reading_pause

        # Adicionar tempo extra no final
        self.total_duration_ms = current_time + 1500
        self.total_frames = max(1, int(math.ceil(self.total_duration_ms / 1000.0 * self.fps)))

    def _estimate_msg_height(self, msg: Message) -> float:
        """Estima a altura de uma mensagem em pixels."""
        if msg.type == MessageType.DATE_SEPARATOR:
            return 40
        if msg.type == MessageType.IMAGE:
            return 280
        if msg.type == MessageType.AUDIO:
            return 70

        text_len = len(msg.text or "")
        # Estimar linhas: ~35 chars por linha em tela de 1080px
        lines = max(1, math.ceil(text_len / 35))
        return 40 + lines * 22

    def get_frame_state(self, frame_index: int) -> FrameState:
        """Calcula o estado completo para um frame específico."""
        t_ms = frame_index * (1000.0 / self.fps)
        state = FrameState()

        # Calcular scroll
        state.scroll_y = self._compute_scroll(t_ms)

        # Verificar cada mensagem
        for event in self.events:
            if t_ms < event.appear_time:
                # Mensagem ainda não apareceu
                continue

            state.visible_messages.append(event.index)

            # Calcular opacidade (animação de aparecimento)
            if t_ms >= event.fully_visible_time:
                state.message_opacity[event.index] = 1.0
                state.message_translate_y[event.index] = 0.0
            else:
                progress = (t_ms - event.appear_time) / max(
                    1, event.fully_visible_time - event.appear_time
                )
                eased = ease_out_cubic(progress)
                state.message_opacity[event.index] = eased

                if self.animation_style == "slide":
                    state.message_translate_y[event.index] = (1.0 - eased) * 20
                else:
                    state.message_translate_y[event.index] = 0.0

        # Verificar indicador de digitação
        for event in self.events:
            if event.typing_start >= 0 and event.typing_start <= t_ms < event.typing_end:
                state.show_typing = True
                state.typing_sender = event.message.sender
                break

        # Hora na status bar (usar a hora da última mensagem visível)
        if state.visible_messages:
            last_idx = state.visible_messages[-1]
            last_msg = self.messages[last_idx]
            if last_msg.time:
                state.status_bar_time = last_msg.time

        return state

    def _compute_scroll(self, t_ms: float) -> float:
        """Calcula a posição do scroll com easing suave."""
        scroll_y = 0.0

        for event in self.events:
            if t_ms < event.scroll_start:
                break

            if t_ms >= event.scroll_end:
                scroll_y = event.target_scroll_y
            else:
                # Em transição de scroll
                progress = (t_ms - event.scroll_start) / max(
                    1, event.scroll_end - event.scroll_start
                )
                eased = ease_in_out_cubic(progress)

                # Interpolar entre scroll anterior e target
                prev_scroll = self.events[event.index - 1].target_scroll_y if event.index > 0 else 0
                scroll_y = prev_scroll + (event.target_scroll_y - prev_scroll) * eased

        return scroll_y
