from typing import List, Dict, Any
import re
from rapidfuzz import fuzz

class PostProcessor:
    def __init__(self):
        # Dicionário simples de correções comuns de OCR
        self.corrections = {
            "0i": "Oi",
            "ta": "Tá",
            "voce": "Você",
            "você": "Você",
            "vocé": "Você",
            "tbm": "também",
            "eh": "é",
            "gue": "que",
            "guerido": "querido",
            "agui": "aqui",
            "aguarde": "aguarde",
            # Correções pontuais de OCR observadas neste tipo de vídeo
            "sii": "Sim",
            "tudc": "tudo",
            "fein": "nem",
            "ai1g": "ai",
            "aig": "ai",
            "áig": "ai",
            "ne19": "ne",
            "mexendc": "mexendo",
        }

        # Marcas d'água / textos de UI que não fazem parte da conversa
        self.watermark_patterns = [
            r"(?i)tiktok",
            r"(?i)historias\s*de\s*zap",
            r"(?i)historiasdezap",
            r"(?i)hist[oó]ria[s]?",
            r"(?i)fake\s*chat",
            r"@\w+",
        ]
        # Palavras-base de marca d'água (removidas por SEMELHANÇA, p/ pegar erros
        # de OCR tipo "historla", "hstotal", "Catorlal", "hisitoria")
        self.watermark_fuzzy = ["historia", "historiasdezap", "tiktok", "fakechat"]

        # Mensagens de sistema do WhatsApp (não fazem parte da conversa)
        self.system_patterns = [
            r"(?i)criptografi",
            r"(?i)protegid[ao]s",
            r"(?i)^\s*hoje\s*$",
            r"(?i)^\s*ontem\s*$",
            r"(?i)mensagens?\s+e\s+as\s+chamadas",
        ]

    def _is_system_message(self, text: str) -> bool:
        for pat in self.system_patterns:
            if re.search(pat, text):
                return True
        return False

    def _correct_word(self, word: str) -> str:
        m = re.match(r'^(\W*)(.*?)(\W*)$', word, re.S)
        if not m:
            return word
        pre, core, post = m.group(1), m.group(2), m.group(3)
        low = core.lower()
        if low in self.corrections:
            rep = self.corrections[low]
            # Preserva capitalização se a primeira letra for maiúscula
            if core[:1].isupper():
                rep = rep.capitalize()
            return pre + rep + post
        return word

    def process_text(self, text: str) -> str:
        """Aplica correções e limpezas rápidas em um texto extraído."""
        # Remove marcas d'água / textos de rede social
        for pat in self.watermark_patterns:
            text = re.sub(pat, " ", text)

        # Remove arrobas soltas que sobraram de @usuario
        text = text.replace("@", " ")

        # Remove tokens parecidos com marcas d'água (erros de OCR)
        kept = []
        for tok in text.split():
            base = re.sub(r"[^a-zà-úA-ZÀ-Ú]", "", tok).lower()
            if len(base) >= 5 and any(fuzz.ratio(base, w) >= 80 for w in self.watermark_fuzzy):
                continue  # descarta token de marca d'água
            kept.append(tok)
        text = " ".join(kept)

        # Remove horários completos (ex: 19:13)
        text = re.sub(r"\b\d{1,2}\s*[:.;,]\s*\d{2}\b", " ", text)
        # Remove dígitos colados no FINAL de palavras (ex: "ne19" -> "ne", "ai9" -> "ai")
        text = re.sub(r"(?<=[a-zà-úA-ZÀ-Ú])\d{1,2}\b", "", text)
        # Remove números soltos de 1-2 dígitos (sobras de horário) e "19:" solto
        text = re.sub(r"\b\d{1,2}\s*[:.;]?\b", " ", text)

        words = re.split(r"(\s+)", text)
        corrected_words = [self._correct_word(w) for w in words]
        text = "".join(corrected_words)

        # Limpezas finais: pontuação solta sobrando de horários, espaços, etc.
        text = re.sub(r"\s+([?!.,])", r"\1", text)   # espaço antes de pontuação
        text = re.sub(r"[:;]+(?=\s|$)", "", text)      # dois-pontos solto
        text = re.sub(r"\s+", " ", text).strip(" :;-@.,")
        return text

    def _looks_like_garbage(self, text: str) -> bool:
        """Detecta lixo de OCR (texto borrado de transições de scroll)."""
        tokens = text.split()
        if not tokens:
            return True

        for t in tokens:
            cleaned = re.sub(r"[^a-zA-Zà-úÀ-Ú]", "", t)
            low = cleaned.lower()
            if not low:
                continue
            # Risadas/expressões repetidas não são lixo (kkk, haha, rsrs...)
            if re.fullmatch(r"(k{2,}|(ha){2,}|(he){2,}|(hi){2,}|(rs){2,}|(hue){2,}|a{3,}|s{3,})", low):
                continue
            # Palavra muito longa sem espaço = quase sempre lixo de OCR
            if len(cleaned) >= 18:
                return True
            # 3+ letras iguais seguidas (ex: "vioullltile")
            if re.search(r"(.)\1\1", low):
                return True
            # 5+ consoantes seguidas (ex: lixo de OCR)
            if re.search(r"[bcdfgjklmnpqrstvwxyzç]{5,}", low):
                return True

        letras = re.findall(r"[a-zà-úA-ZÀ-Ú]", text)
        if len(letras) >= 6:
            vogais = re.findall(r"[aeiouáéíóúãõâêîôûàAEIOUÁÉÍÓÚÃÕÂÊÎÔÛÀ]", text)
            ratio = len(vogais) / len(letras)
            # Português real fica ~0.40-0.50 de vogais. Fora de 0.25-0.72 = suspeito
            if ratio < 0.25 or ratio > 0.72:
                return True

        return False

    def _is_valid_message(self, text: str) -> bool:
        """Verifica se o texto possui o mínimo de coerência (evita lixos de borda)."""
        if not text or len(text.strip()) < 2:
            return False

        # Textos reais em português devem ter vogais
        if not re.search(r"[aeiouyáéíóúãõâêîôûà]", text.lower()):
            return False

        # Tem que ter ao menos 2 letras alfabéticas
        letras = re.findall(r"[a-zA-Záéíóúãõâêîôûàç]", text.lower())
        if len(letras) < 2:
            return False

        if self._looks_like_garbage(text):
            return False

        return True

    def finalize_conversation(self, unique_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Faz as limpezas finais e retorna o layout correto para exportação JSON.
        unique_messages: [{"author": "USER_1", "text": "...", "frame": 10, "y": 150}]
        """
        final_convo = []
        for msg in unique_messages:
            if self._is_system_message(msg["text"]):
                continue
            final_text = self.process_text(msg["text"])
            if self._is_system_message(final_text):
                continue
            if self._is_valid_message(final_text):
                final_convo.append({
                    "author": msg["author"],
                    "texto": final_text,
                })
        return final_convo
