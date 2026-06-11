"""Parser de conversas — suporta TXT, JSON e CSV.
Copiado e adaptado do api/parser.py original.
"""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Optional


# ── Modelos inline (simples, sem Pydantic pesado no web service) ──

class Message:
    __slots__ = ("sender", "text", "time", "type", "media_path", "status")

    def __init__(
        self,
        sender: str,
        text: Optional[str] = None,
        time: str = "12:00",
        type: str = "text",
        media_path: Optional[str] = None,
        status: str = "read",
    ):
        self.sender = sender
        self.text = text
        self.time = time
        self.type = type
        self.media_path = media_path
        self.status = status

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "text": self.text,
            "time": self.time,
            "type": self.type,
            "media_path": self.media_path,
            "status": self.status,
        }


def parse_conversation(content: str, filename: str = "conversation.txt") -> list[Message]:
    """Detecta o formato e parseia a conversa."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext == "json":
        return _parse_json(content)
    elif ext == "csv":
        return _parse_csv(content)
    else:
        return _parse_txt(content)


def _parse_txt(content: str) -> list[Message]:
    messages: list[Message] = []
    lines = content.strip().split("\n")
    msg_pattern = re.compile(r"^\[(\d{1,2}:\d{2})\]\s+(.+?):\s+(.+)$")
    cmd_pattern = re.compile(r"^\[(IMAGE|EMOJI|AUDIO|DATE)\]\s+(.+)$", re.IGNORECASE)

    current_time = "12:00"
    current_sender: Optional[str] = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        cmd_match = cmd_pattern.match(line)
        if cmd_match:
            cmd_type = cmd_match.group(1).upper()
            cmd_value = cmd_match.group(2).strip()
            if cmd_type == "IMAGE":
                messages.append(Message(sender=current_sender or "me", time=current_time, type="image", media_path=cmd_value))
            elif cmd_type == "EMOJI":
                messages.append(Message(sender=current_sender or "me", text=cmd_value, time=current_time, type="emoji"))
            elif cmd_type == "AUDIO":
                messages.append(Message(sender=current_sender or "me", time=current_time, type="audio", media_path=cmd_value))
            elif cmd_type == "DATE":
                messages.append(Message(sender="system", text=cmd_value, time="", type="date_separator"))
            continue

        msg_match = msg_pattern.match(line)
        if msg_match:
            current_time = msg_match.group(1)
            current_sender = msg_match.group(2).strip()
            text = msg_match.group(3).strip()
            messages.append(Message(sender=current_sender, text=text, time=current_time, type="text"))

    _assign_me_sender(messages)
    return messages


def _assign_me_sender(messages: list[Message]) -> None:
    senders: list[str] = []
    for msg in messages:
        if msg.sender != "system" and msg.sender not in senders:
            senders.append(msg.sender)
        if len(senders) >= 2:
            break
    if len(senders) >= 2:
        me_name = senders[1]
        for msg in messages:
            if msg.sender == me_name:
                msg.sender = "me"


def _parse_json(content: str) -> list[Message]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido: {e}")
    if not isinstance(data, list):
        raise ValueError("JSON deve ser um array de mensagens")
    return [
        Message(
            sender=item.get("sender", "me"),
            text=item.get("text") or item.get("message"),
            time=item.get("time", "12:00"),
            type=item.get("type", "text"),
            media_path=item.get("media_path"),
            status=item.get("status", "read"),
        )
        for item in data
    ]


def _parse_csv(content: str) -> list[Message]:
    reader = csv.DictReader(io.StringIO(content))
    return [
        Message(
            sender=row.get("sender", "me"),
            text=row.get("message") or row.get("text"),
            time=row.get("time", "12:00"),
            type=row.get("type", "text"),
            media_path=row.get("media_path") or None,
            status=row.get("status", "read"),
        )
        for row in reader
    ]
