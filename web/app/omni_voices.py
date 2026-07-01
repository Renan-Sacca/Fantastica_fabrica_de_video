"""Gerenciamento de vozes de referência do OmniVoice (clonagem).

ATUALIZADO: Agora usa banco de dados MySQL ao invés de arquivo JSON.
As vozes são salvas por usuário e respeitam os limites do plano.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import List, Optional

from app.config import OMNI_VOICES_DIR
from app.repositories import user_voices as voices_repo


def _slugify(name: str) -> str:
    """Converte nome em slug seguro para nome de arquivo."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "voz"


def list_custom(user_id: int) -> List[dict]:
    """
    Lista todas as vozes personalizadas de um usuário.
    Retorna lista de dicts com id, name, filename, reference_text.
    """
    voices = voices_repo.get_user_voices(user_id)
    result = []
    for voice in voices:
        # Verifica se o arquivo existe fisicamente
        if (OMNI_VOICES_DIR / voice["filename"]).exists():
            result.append({
                "id": voice["voice_id"],
                "name": voice["name"],
                "filename": voice["filename"],
                "reference_text": voice.get("reference_text", ""),
            })
    return sorted(result, key=lambda v: v["name"].lower())


def save_custom(
    user_id: int,
    name: str,
    content: bytes,
    original_filename: str,
    reference_text: str,
    max_voices: int,
    is_unlimited: bool,
) -> dict:
    """
    Salva uma nova voz personalizada.
    
    Args:
        user_id: ID do usuário
        name: Nome da voz
        content: Bytes do arquivo de áudio
        original_filename: Nome original do arquivo enviado
        reference_text: Texto de referência (opcional)
        max_voices: Limite de vozes do plano
        is_unlimited: Se o plano é ilimitado
    
    Returns:
        dict com id, name, filename
        
    Raises:
        ValueError: Se o usuário atingiu o limite de vozes
    """
    # Verifica limite do plano
    if not voices_repo.check_voice_limit(user_id, max_voices, is_unlimited):
        raise ValueError(f"Limite de {max_voices} vozes atingido para este plano.")
    
    # Prepara arquivo
    OMNI_VOICES_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix.lower() or ".wav"
    voice_id = uuid.uuid4().hex[:8]
    filename = f"omni_u{user_id}_{_slugify(name)}_{voice_id}{ext}"

    # Salva arquivo físico
    (OMNI_VOICES_DIR / filename).write_bytes(content)

    # Salva no banco de dados
    voice = voices_repo.create_voice(
        voice_id=voice_id,
        user_id=user_id,
        name=name.strip(),
        filename=filename,
        reference_text=(reference_text or "").strip(),
    )

    return {"id": voice["voice_id"], "name": voice["name"], "filename": voice["filename"]}


def get_custom(voice_id: str, user_id: Optional[int] = None) -> dict | None:
    """
    Retorna informações de uma voz específica.
    
    Args:
        voice_id: ID da voz
        user_id: ID do usuário (opcional, para verificação de propriedade)
    
    Returns:
        dict com id, name, filename, reference_text ou None
    """
    voice = voices_repo.get_voice(voice_id)
    if not voice:
        return None
    
    # Verifica propriedade se user_id foi fornecido
    if user_id is not None and voice["user_id"] != user_id:
        return None
    
    # Verifica se arquivo existe
    if not (OMNI_VOICES_DIR / voice["filename"]).exists():
        return None
    
    return {
        "id": voice["voice_id"],
        "name": voice["name"],
        "filename": voice["filename"],
        "reference_text": voice.get("reference_text", ""),
    }


def delete_custom(voice_id: str, user_id: int) -> bool:
    """
    Deleta uma voz personalizada (soft delete no banco + remoção do arquivo).
    
    Args:
        voice_id: ID da voz
        user_id: ID do usuário (para verificar propriedade)
    
    Returns:
        True se deletado com sucesso, False caso contrário
    """
    voice = voices_repo.get_voice(voice_id)
    if not voice:
        return False
    
    # Verifica propriedade
    if voice["user_id"] != user_id:
        return False
    
    # Soft delete no banco
    if not voices_repo.soft_delete_voice(voice_id):
        return False
    
    # Remove arquivo físico (best-effort)
    try:
        (OMNI_VOICES_DIR / voice["filename"]).unlink(missing_ok=True)
    except Exception:
        pass
    
    return True
