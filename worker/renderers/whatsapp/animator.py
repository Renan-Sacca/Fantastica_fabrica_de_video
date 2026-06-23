"""Animator — adaptado para o worker (importa de renderers.whatsapp.models)."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from renderers.whatsapp.models import Message, MessageType


@dataclass
class MessageEvent:
    index: int
    message: Message
    appear_time: float
    fully_visible_time: float
    typing_start: float
    typing_end: float
    scroll_start: float
    scroll_end: float
    target_scroll_y: float


@dataclass
class FrameState:
    scroll_y: float = 0.0
    visible_messages: list[int] = field(default_factory=list)
    message_opacity: dict[int, float] = field(default_factory=dict)
    message_translate_y: dict[int, float] = field(default_factory=dict)
    message_scale: dict[int, float] = field(default_factory=dict)
    show_typing: bool = False
    typing_sender: str = ""
    status_bar_time: str = "10:30"


def ease_in_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 4.0 * t * t * t
    return 1.0 - pow(-2.0 * t + 2.0, 3) / 2.0


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - pow(1.0 - t, 3)


def humanize(value: float, variation: float = 0.20, rng: Optional[random.Random] = None) -> float:
    r = rng or random
    return value * (1.0 + r.uniform(-variation, variation))


class Timeline:
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

    def _get_typing_duration(self, msg: Message) -> float:
        text_len = len(msg.text or "")
        return humanize(min(500 + text_len * 15, 2000), rng=self.rng) / self.speed

    def _get_scroll_duration(self) -> float:
        return humanize(450, rng=self.rng) / self.scroll_speed

    def _estimate_msg_height(self, msg: Message) -> float:
        if msg.type == MessageType.DATE_SEPARATOR:
            return 44.0
        if msg.type == MessageType.IMAGE:
            if msg.media_path:
                try:
                    from PIL import Image
                    with Image.open(msg.media_path) as img:
                        w, h = img.size
                        # A imagem no CSS tem max-width: 300px e max-height: 350px
                        # E ela ocupa 100% do container (que é até 300px)
                        img_height = min(350.0, 300.0 * (h / max(1, w)))
                        return img_height + 10.0 # margin/padding bounds
                except Exception:
                    pass
            return 300.0
        if msg.type == MessageType.AUDIO:
            return 60.0
        text_len = len(msg.text or "")
        lines = max(1, math.ceil(text_len / 42.0))
        return 28.0 + lines * 21.0

    def _build_timeline(self) -> None:
        current_time = 500.0
        accumulated_height = 0.0
        num_messages = len(self.messages)
        for i, msg in enumerate(self.messages):
            delay = self._get_message_delay(msg)
            current_time += delay
            typing_start = -1.0
            typing_end = -1.0
            if msg.sender != "me" and msg.type == MessageType.TEXT and self.animation_style == "typing":
                dur = self._get_typing_duration(msg)
                typing_start = current_time
                typing_end = current_time + dur
                current_time = typing_end
            anim_dur = humanize(350, variation=0.1, rng=self.rng)
            appear_time = current_time
            fully_visible_time = current_time + anim_dur
            accumulated_height += self._estimate_msg_height(msg)
            # Para a última mensagem usa padding maior para garantir que fique
            # completamente acima da barra de input (altura estimada pode ser menor que a real).
            is_last = (i == num_messages - 1)
            extra_padding = 80.0 if is_last else 25.0
            target_scroll = max(0.0, accumulated_height - self.usable_height + extra_padding)
            scroll_dur = self._get_scroll_duration()
            self.events.append(MessageEvent(
                index=i, message=msg, appear_time=appear_time,
                fully_visible_time=fully_visible_time,
                typing_start=typing_start, typing_end=typing_end,
                scroll_start=appear_time, scroll_end=appear_time + scroll_dur,
                target_scroll_y=target_scroll,
            ))
            current_time = fully_visible_time + self._get_reading_pause(msg)
        # Buffer final: garante frames suficientes depois da última mensagem aparecer
        self.total_duration_ms = current_time + 5000.0
        self.total_frames = max(1, int(math.ceil(self.total_duration_ms / 1000.0 * self.fps)))

    def get_frame_state(self, frame_index: int) -> FrameState:
        t_ms = frame_index * (1000.0 / self.fps)
        state = FrameState()
        state.scroll_y = self._compute_scroll(t_ms)
        for event in self.events:
            if t_ms < event.appear_time:
                continue
            state.visible_messages.append(event.index)
            if t_ms >= event.fully_visible_time:
                state.message_opacity[event.index] = 1.0
                state.message_translate_y[event.index] = 0.0
                state.message_scale[event.index] = 1.0
            else:
                progress = (t_ms - event.appear_time) / max(1, event.fully_visible_time - event.appear_time)
                eased = ease_out_cubic(progress)

                if self.animation_style == "fade":
                    # Fade puro: só opacidade, sem movimento
                    state.message_opacity[event.index] = eased
                    state.message_translate_y[event.index] = 0.0
                    state.message_scale[event.index] = 1.0

                elif self.animation_style == "slide":
                    # Slide: sobe 40px enquanto aparece (mais exagerado para ser visível)
                    state.message_opacity[event.index] = eased
                    state.message_translate_y[event.index] = (1.0 - eased) * 40.0
                    state.message_scale[event.index] = 1.0

                elif self.animation_style == "typing":
                    # Typing: mensagem "pop in" — escala de 0.7→1 + fade
                    state.message_opacity[event.index] = eased
                    state.message_translate_y[event.index] = 0.0
                    state.message_scale[event.index] = 0.7 + eased * 0.3  # 0.7→1.0

        for event in self.events:
            if event.typing_start >= 0 and event.typing_start <= t_ms < event.typing_end:
                state.show_typing = True
                state.typing_sender = event.message.sender
                break
        if state.visible_messages:
            last_msg = self.messages[state.visible_messages[-1]]
            if last_msg.time:
                state.status_bar_time = last_msg.time
        return state

    def _compute_scroll(self, t_ms: float) -> float:
        scroll_y = 0.0
        for event in self.events:
            if t_ms < event.scroll_start:
                break
            if t_ms >= event.scroll_end:
                scroll_y = event.target_scroll_y
            else:
                progress = (t_ms - event.scroll_start) / max(1, event.scroll_end - event.scroll_start)
                eased = ease_in_out_cubic(progress)
                prev = self.events[event.index - 1].target_scroll_y if event.index > 0 else 0
                scroll_y = prev + (event.target_scroll_y - prev) * eased
        return scroll_y
