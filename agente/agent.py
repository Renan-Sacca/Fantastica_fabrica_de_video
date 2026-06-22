"""Agente de correção de texto — envia texto para a IA e retorna a correção.

Diferente do agent.py do SPEC (que tem tool loop), este agente é simples:
apenas envia o prompt de correção e retorna a resposta, sem executar ferramentas.
"""
from __future__ import annotations

import asyncio
import logging

from browser import BrowserEngine

logger = logging.getLogger("TextCorrectionAgent")

CORRECTION_PROMPT = """Atue como um revisor de texto especializado em transcrições de OCR. 

Instruções:
1. Retorne APENAS o texto final corrigido. Não inclua nenhuma introdução, explicações, resumos ou comentários antes ou depois do texto.
2. Corrija a ortografia, acentuação e pontuação do texto abaixo.
3. Identifique e complete palavras que pareçam cortadas ou mal interpretadas pelo scanner.
4. Remova linhas ou trechos duplicados gerados por falha de leitura.
5. Remova COMPLETAMENTE qualquer linha que contenha palavras ou termos incompreensíveis (em vez de marcar como [Incompreensível], delete a linha inteira).
6. Mantenha a estrutura original do diálogo.
7. Remova palavras ofensivas ou desnecessárias, não exclua a linha troque por palavras mais leves.

Texto para correção:
{text}"""


class TextCorrectionAgent:
    """Agente que corrige texto via ChatGPT ou Gemini."""

    def __init__(self, browser: BrowserEngine):
        self.browser = browser

    async def correct_text(self, raw_text: str, provider: str) -> str:
        """Envia o texto bruto para a IA e retorna o texto corrigido.

        Args:
            raw_text: Texto bruto (transcrição OCR, conversa de WhatsApp, etc.)
            provider: 'chatgpt' ou 'gemini'

        Returns:
            Texto corrigido pela IA.

        Raises:
            RuntimeError: Se não conseguir obter resposta da IA.
        """
        # Trocar provider se necessário
        await self.browser.switch_provider(provider)

        # Montar prompt
        prompt = CORRECTION_PROMPT.format(text=raw_text)

        logger.info(f"Enviando texto ({len(raw_text)} chars) para {provider}")

        # Enviar e aguardar resposta
        response = await self.browser.send_message(prompt)

        if not response:
            raise RuntimeError("IA retornou resposta vazia.")

        if self.browser.is_rate_limited(response):
            logger.warning("Rate limit detectado — aguardando 30s e tentando novamente")
            await asyncio.sleep(30)
            response = await self.browser.send_message(prompt)

            if not response or self.browser.is_rate_limited(response):
                raise RuntimeError("Rate limit persistente. Tente novamente mais tarde.")

        logger.info(f"Resposta recebida ({len(response)} chars)")
        return response
