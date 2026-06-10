"""Parser de conversas - suporta TXT, JSON e CSV."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Optional

from api.models import Message, MessageStatus, MessageType


def parse_conversation(content: str, filename: str = "conversation.txt") -> list[Message]:
    """Detecta formato e parseia a conversa."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    if ext == "json":
        return _parse_json(content)
    elif ext == "csv":
        return _parse_csv(content)
    else:
        return _parse_txt(content)


def _parse_txt(content: str) -> list[Message]:
    """
    Parseia formato TXT estruturado.

    Formatos suportados:
        [HH:MM] Nome: Mensagem
        [IMAGE] caminho/imagem.jpg
        [EMOJI] 😀
        [AUDIO] caminho/audio.mp3
        [DATE] 10 de Junho de 2024
    """
    messages: list[Message] = []
    lines = content.strip().split("\n")

    # Regex para mensagem normal: [10:30] João: Olá, tudo bem?
    msg_pattern = re.compile(
        r"^\[(\d{1,2}:\d{2})\]\s+(.+?):\s+(.+)$"
    )

    # Regex para comandos especiais: [IMAGE] path, [EMOJI] emoji, etc.
    cmd_pattern = re.compile(
        r"^\[(IMAGE|EMOJI|AUDIO|DATE)\]\s+(.+)$", re.IGNORECASE
    )

    current_time = "12:00"
    current_sender: Optional[str] = None
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Tentar match de comando especial
        cmd_match = cmd_pattern.match(line)
        if cmd_match:
            cmd_type = cmd_match.group(1).upper()
            cmd_value = cmd_match.group(2).strip()

            if cmd_type == "IMAGE":
                messages.append(Message(
                    sender=current_sender or "me",
                    text=None,
                    time=current_time,
                    type=MessageType.IMAGE,
                    media_path=cmd_value,
                    status=MessageStatus.READ,
                ))
            elif cmd_type == "EMOJI":
                messages.append(Message(
                    sender=current_sender or "me",
                    text=cmd_value,
                    time=current_time,
                    type=MessageType.EMOJI,
                    status=MessageStatus.READ,
                ))
            elif cmd_type == "AUDIO":
                messages.append(Message(
                    sender=current_sender or "me",
                    text=None,
                    time=current_time,
                    type=MessageType.AUDIO,
                    media_path=cmd_value,
                    status=MessageStatus.READ,
                ))
            elif cmd_type == "DATE":
                messages.append(Message(
                    sender="system",
                    text=cmd_value,
                    time="",
                    type=MessageType.DATE_SEPARATOR,
                    status=MessageStatus.READ,
                ))

            i += 1
            continue

        # Tentar match de mensagem normal
        msg_match = msg_pattern.match(line)
        if msg_match:
            current_time = msg_match.group(1)
            current_sender = msg_match.group(2).strip()
            text = msg_match.group(3).strip()

            messages.append(Message(
                sender=current_sender,
                text=text,
                time=current_time,
                type=MessageType.TEXT,
                status=MessageStatus.READ,
            ))

            i += 1
            continue

        # Linha não reconhecida - pular
        i += 1

    # Determinar quem é "me" (o primeiro remetente que não seja "system")
    # A primeira pessoa que fala é assumida como o contato, a segunda como "me"
    _assign_me_sender(messages)

    return messages


def _assign_me_sender(messages: list[Message]) -> None:
    """
    Identifica os participantes e marca o segundo como 'me'.
    Em uma conversa de 2 pessoas, o segundo participante é o usuário.
    """
    senders = []
    for msg in messages:
        if msg.sender != "system" and msg.sender not in senders:
            senders.append(msg.sender)
        if len(senders) >= 2:
            break

    if len(senders) >= 2:
        me_name = senders[1]  # Segundo participante = "me"
        for msg in messages:
            if msg.sender == me_name:
                msg.sender = "me"


def _parse_json(content: str) -> list[Message]:
    """
    Parseia formato JSON.

    Formato esperado:
    [
        {"sender": "João", "text": "Olá!", "time": "10:30", "type": "text"},
        {"sender": "me", "text": null, "time": "10:31", "type": "image", "media_path": "foto.jpg"}
    ]
    """
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}")

    if not isinstance(data, list):
        raise ValueError("JSON deve ser um array de mensagens")

    messages = []
    for item in data:
        msg = Message(
            sender=item.get("sender", "me"),
            text=item.get("text") or item.get("message"),
            time=item.get("time", "12:00"),
            type=MessageType(item.get("type", "text")),
            media_path=item.get("media_path"),
            status=MessageStatus(item.get("status", "read")),
        )
        messages.append(msg)

    return messages


def _parse_csv(content: str) -> list[Message]:
    """
    Parseia formato CSV.

    Colunas esperadas: time,sender,message,type,media_path
    """
    reader = csv.DictReader(io.StringIO(content))
    messages = []

    for row in reader:
        msg = Message(
            sender=row.get("sender", "me"),
            text=row.get("message") or row.get("text"),
            time=row.get("time", "12:00"),
            type=MessageType(row.get("type", "text")),
            media_path=row.get("media_path") or None,
            status=MessageStatus(row.get("status", "read")),
        )
        messages.append(msg)

    return messages
