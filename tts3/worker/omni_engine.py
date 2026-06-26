"""Wrapper do modelo OmniVoice (k2-fsa) rodando na GPU."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("OmniEngine")

MODEL_NAME = "k2-fsa/OmniVoice"

# Parâmetros de geração aceitos pelo model.generate(...)
GEN_PARAM_KEYS = [
    "num_step",
    "denoise",
    "guidance_scale",
    "t_shift",
    "position_temperature",
    "class_temperature",
    "layer_penalty_factor",
    "speed",
    "duration",
    "preprocess_prompt",
    "postprocess_output",
    "audio_chunk_duration",
    "audio_chunk_threshold",
    "language_id",
]


class OmniEngine:
    def __init__(self) -> None:
        self._model = None
        self._device = "cpu"

    def load(self) -> None:
        import torch
        from omnivoice import OmniVoice

        if torch.cuda.is_available():
            self._device = "cuda:0"
            dtype = torch.float16
            logger.info(f"GPU detectada: {torch.cuda.get_device_name(0)}")
        else:
            self._device = "cpu"
            dtype = torch.float32
            logger.warning("CUDA indisponível — usando CPU (lento).")

        logger.info(f"Carregando modelo {MODEL_NAME}...")
        self._model = OmniVoice.from_pretrained(
            MODEL_NAME, device_map=self._device, dtype=dtype
        )
        logger.info("Modelo OmniVoice carregado.")

    @property
    def sample_rate(self) -> int:
        return 24000

    def generate(
        self,
        text: str,
        mode: str,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        instruct: Optional[str] = None,
        gen_params: Optional[dict] = None,
    ):
        """Gera o áudio. Retorna um np.ndarray (T,) a 24kHz.

        mode: "clone" | "design" | "auto"
        """
        if self._model is None:
            raise RuntimeError("Modelo não carregado. Chame load() antes.")

        kwargs = {"text": text}

        if mode == "clone":
            if not ref_audio:
                raise ValueError("Clonagem requer um áudio de referência.")
            kwargs["ref_audio"] = ref_audio
            if ref_text:
                kwargs["ref_text"] = ref_text  # senão o Whisper transcreve sozinho
        elif mode == "design":
            if not instruct:
                raise ValueError("Voice Design requer atributos (instruct).")
            kwargs["instruct"] = instruct
        # mode == "auto": nenhum prompt de voz

        # Parâmetros de geração (apenas os informados)
        if gen_params:
            for key in GEN_PARAM_KEYS:
                if key in gen_params and gen_params[key] is not None:
                    kwargs[key] = gen_params[key]

        audio = self._model.generate(**kwargs)
        # generate retorna uma lista de np.ndarray
        return audio[0]
