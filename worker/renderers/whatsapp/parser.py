"""Parser de conversas para o worker WhatsApp."""
from __future__ import annotations

import csv
import io
import json
import re
from typing import Optional

from renderers.whatsapp.models import Message, MessageStatus, MessageType


def parse_conversation(content: str, filename: str = "conversa.txt") -> list[Message]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext == "json":
        return _parse_json(content)
    elif ext == "csv":
        return _parse_csv(content)
    return _parse_txt(content)


def _parse_txt(content: str) -> list[Message]:
    messages: list[Message] = []
    msg_pattern = re.compile(r"^\[(\d{1,2}:\d{2})\]\s+(.+?):\s+(.+)$")
    cmd_pattern = re.compile(r"^\[(IMAGE|EMOJI|AUDIO|DATE)\]\s+(.+)$", re.IGNORECASE)

    current_time = "12:00"
    current_sender: Optional[str] = None

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        cmd = cmd_pattern.match(line)
        if cmd:
            t, v = cmd.group(1).upper(), cmd.group(2).strip()
            if t == "IMAGE":
                messages.append(Message(sender=current_sender or "me", time=current_time, type=MessageType.IMAGE, media_path=v))
            elif t == "EMOJI":
                messages.append(Message(sender=current_sender or "me", text=v, time=current_time, type=MessageType.EMOJI))
            elif t == "AUDIO":
                messages.append(Message(sender=current_sender or "me", time=current_time, type=MessageType.AUDIO, media_path=v))
            elif t == "DATE":
                messages.append(Message(sender="system", text=v, time="", type=MessageType.DATE_SEPARATOR))
            continue

        m = msg_pattern.match(line)
        if m:
            current_time = m.group(1)
            current_sender = m.group(2).strip()
            messages.append(Message(sender=current_sender, text=m.group(3).strip(), time=current_time, type=MessageType.TEXT))

    _assign_me(messages)
    return messages


def _assign_me(messages: list[Message]) -> None:
    senders: list[str] = []
    for msg in messages:
        if msg.sender != "system" and msg.sender not in senders:
            senders.append(msg.sender)
        if len(senders) >= 2:
            break
    if len(senders) >= 2:
        for msg in messages:
            if msg.sender == senders[1]:
                msg.sender = "me"


def _parse_json(content: str) -> list[Message]:
    data = json.loads(content)
    if not isinstance(data, list):
        raise ValueError("JSON deve ser um array de mensagens")
    return [
        Message(
            sender=item.get("sender", "me"),
            text=item.get("text") or item.get("message"),
            time=item.get("time", "12:00"),
            type=MessageType(item.get("type", "text")),
            media_path=item.get("media_path"),
            status=MessageStatus(item.get("status", "read")),
        )
        for item in data
    ]


def _parse_csv(content: str) -> list[Message]:
    return [
        Message(
            sender=row.get("sender", "me"),
            text=row.get("message") or row.get("text"),
            time=row.get("time", "12:00"),
            type=MessageType(row.get("type", "text")),
            media_path=row.get("media_path") or None,
        )
        for row in csv.DictReader(io.StringIO(content))
    ]
