from typing import List, Dict, Any
from rapidfuzz import fuzz
import re
import unicodedata

class Deduplicator:
    def __init__(self, similarity_threshold: float = 80.0):
        self.similarity_threshold = similarity_threshold

    def _strip_accents(self, text: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))

    def _normalize_text(self, text: str) -> str:
        """Normaliza o texto removendo espaços extras, quebras de linha e pontuações para melhorar a comparação."""
        if not text:
            return ""
        # Remove acentos (OCR oscila entre "náo"/"nao", "vé"/"ve")
        text = self._strip_accents(text)
        # Remove pontuações
        text = re.sub(r'[^\w\s]', '', text)
        # Remove números, pois OCR confunde pontuação no final com horas, o que quebra a similaridade (ex: "Kkkkk 19")
        text = re.sub(r'\d+', '', text)
        # Substitui multiplos espaços e quebras por apenas um espaço
        text = re.sub(r'\s+', ' ', text)
        return text.strip().lower()

    def remove_duplicates(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        messages: [{ "author": "USER_1", "text": "Oi", "y": 100, "frame": 5 }, ...]
        Retorna uma lista de mensagens sem duplicatas, baseando-se em similaridade do RapidFuzz
        e confirmando através do autor.
        """
        if not messages:
            return []

        # Ordena as mensagens primeiramente pelo frame e secundariamente pelo Y (de cima para baixo)
        messages = sorted(messages, key=lambda m: (m['frame'], m['y']))
        
        unique_messages = []
        
        for msg in messages:
            norm_text = self._normalize_text(msg['text'])
            if not norm_text:
                continue
                
            is_duplicate = False
            
            # Comparamos só com as últimas mensagens inseridas (janela curta):
            # uma mensagem reaparece em frames próximos durante o scroll, então
            # não precisa comparar com mensagens distantes — e isso evita juntar
            # por engano mensagens diferentes (o que bagunçava a ordem).
            window = unique_messages[-15:] if len(unique_messages) > 15 else unique_messages
            
            for idx, existing in enumerate(window):
                existing_norm = self._normalize_text(existing['text'])

                similarity = fuzz.ratio(norm_text, existing_norm)
                partial_sim = fuzz.partial_ratio(norm_text, existing_norm)
                token_sim = fuzz.token_set_ratio(norm_text, existing_norm)

                la, lb = len(norm_text), len(existing_norm)
                length_ratio = min(la, lb) / max(la, lb) if max(la, lb) else 0.0

                same_author = existing['author'] == msg['author']

                # Mesmo autor: critério normal (sem guarda de tamanho — uma
                # mensagem cortada na borda da tela aparece truncada num frame
                # e completa em outro; queremos juntá-las).
                strong = (similarity >= self.similarity_threshold or partial_sim >= 85 or token_sim >= 85)
                # Autores diferentes: exige tamanhos parecidos. Senão uma frase
                # curta ("Estressar ele?") casaria com uma longa que contém suas
                # palavras ("...por fazer ele se estressar a cada ano") e seria
                # descartada por engano (bagunçando a ordem).
                cross = (not same_author) and la >= 12 and length_ratio >= 0.6 and (similarity >= 90 or token_sim >= 92)

                if (same_author and strong) or cross:
                    is_duplicate = True
                    # Só substituímos pela leitura mais longa quando é o MESMO
                    # autor. Em match entre autores diferentes (ex: citação/reply
                    # que repete a mensagem do outro), mantemos a primeira (real)
                    # e descartamos a nova — senão a citação sobrescreve o autor.
                    if same_author and len(msg['text'].strip()) > len(existing['text'].strip()):
                        real_idx = len(unique_messages) - len(window) + idx
                        unique_messages[real_idx]['text'] = msg['text']
                        existing['text'] = msg['text']
                    break
            
            if not is_duplicate:
                unique_messages.append(msg)
                
        return unique_messages
