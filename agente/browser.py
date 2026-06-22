"""Motor do navegador — abre Chromium, navega, envia mensagem e extrai resposta.

Baseado no SPEC_NOVO_AGENTE.md, adaptado para rodar headless/Xvfb em Docker.
Suporta ChatGPT e Gemini, com seletores prioritizados por fallback.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext

logger = logging.getLogger("BrowserEngine")

# ── Seletores por provider ──

CHATGPT = {
    "url": "https://chatgpt.com",
    "input": [
        "#prompt-textarea",
        'div[contenteditable="true"]',
        "textarea",
    ],
    "submit": [
        'button[data-testid="send-button"]',
        'button[aria-label="Send message"]',
        'button[aria-label="Send"]',
    ],
    "stop": [
        'button[aria-label="Stop streaming"]',
        'button[data-testid="stop-button"]',
    ],
    "response": [
        '[data-message-author-role="assistant"] .markdown',
        '[data-message-author-role="assistant"]',
        '.agent-turn .markdown',
        '.agent-turn',
    ],
}

GEMINI = {
    "url": "https://gemini.google.com/app",
    "input": [
        'div[role="textbox"]',
        '[contenteditable="true"]',
        'rich-textarea [contenteditable]',
    ],
    "submit": [
        'button[aria-label*="Send"]',
        'button[aria-label*="Enviar"]',
        'send-button button',
    ],
    "stop": [
        'button[aria-label*="Stop"]',
        'button[aria-label*="Parar"]',
    ],
    "response": [
        'model-response .markdown',
        'model-response message-content',
        'div[data-author="model"] .markdown',
        'message-content',
    ],
    # Seletor do toggle "Atividade do Gemini" para desativar histórico (modo anônimo)
    "activity_toggle": [
        'button[aria-label*="Atividade"]',
        'button[aria-label*="Gemini Apps Activity"]',
    ],
}

PROVIDERS = {
    "chatgpt": CHATGPT,
    "gemini": GEMINI,
}

# ── Frases indicando rate limit ──
RATE_LIMIT_PHRASES = [
    "rate limit", "too many requests", "aguarde alguns minutos",
    "you've reached", "usage limit", "tente novamente mais tarde",
]

# ── Lixo de UI a remover da resposta ──
GARBAGE = ["Try again without Canvas", "Try again", "Sources", "Editar"]

# ── Indicadores de página de login ──
LOGIN_INDICATORS = [
    'button:has-text("Sign in")',
    'button:has-text("Log in")',
    'button:has-text("Entrar")',
    'input[type="email"]',
    'input[name="identifier"]',
]

# ── Script Stealth JS para bypass de detecção de bots (Cloudflare, etc.) ──
STEALTH_JS = """
// Sobrescrever navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Sobrescrever navigator.languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['pt-BR', 'pt', 'en-US', 'en']
});

// Sobrescrever navigator.plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5]
});

// Mock de WebGL fingerprint
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    // UNMASKED_VENDOR_WEBGL
    if (parameter === 37445) {
        return 'Intel Inc.';
    }
    // UNMASKED_RENDERER_WEBGL
    if (parameter === 37446) {
        return 'Intel(R) Iris(TM) Plus Graphics 640';
    }
    return getParameter(parameter);
};

// Sobrescrever window.chrome
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Sobrescrever navigator.permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
"""


class BrowserEngine:
    """Controla o Chromium via Playwright para interagir com ChatGPT/Gemini."""

    def __init__(self, provider: str, headless: bool, chrome_data_dir: str):
        self.provider = provider
        self.headless = headless
        self.chrome_data_dir = chrome_data_dir
        self.selectors = PROVIDERS.get(provider, CHATGPT)
        self._playwright = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> None:
        """Inicia o Playwright e abre o navegador com perfil persistente.

        Inclui patches de stealth para evitar detecção por Cloudflare/Turnstile.
        """
        # Limpar travas antigas do Chromium (SingletonLock, SingletonSocket, SingletonCookie)
        import os
        from pathlib import Path
        chrome_dir = Path(self.chrome_data_dir)
        if chrome_dir.exists():
            for item in chrome_dir.iterdir():
                if item.name.startswith("Singleton"):
                    try:
                        if item.is_symlink() or item.is_file():
                            os.unlink(item)
                            logger.info(f"Removido link de trava antigo: {item.name}")
                    except Exception as e:
                        logger.warning(f"Erro ao remover {item.name}: {e}")

        self._playwright = await async_playwright().start()

        # User-Agent real do Chrome 120 no Linux (evita fingerprint do Chromium)
        user_agent = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=self.chrome_data_dir,
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-infobars",
                "--disable-background-networking",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=IsolateOrigins,site-per-process",
                "--window-size=1280,720",
            ],
            user_agent=user_agent,
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )

        # ── Stealth: injetar scripts anti-detecção em toda página ──
        await self._context.add_init_script(script=STEALTH_JS)

        # Usa a primeira página ou cria uma nova
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        logger.info(f"Browser iniciado — provider: {self.provider}, headless: {self.headless}")

    async def navigate_to_chat(self) -> None:
        """Navega até a URL do provider.

        Para Gemini abre sempre uma conversa nova (/app/new) para que cada
        job fique numa thread isolada e possa ser deletada após o uso.
        """
        if self.provider == "gemini":
            url = "https://gemini.google.com/app/new"
        else:
            url = self.selectors["url"]

        logger.info(f"Navegando para {url}")
        await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)

        if await self._needs_login():
            logger.warning(
                "⚠️  Página de login detectada! "
                "Acesse o noVNC (porta 6080) e faça login manualmente."
            )
            raise RuntimeError(
                "Login necessário. Acesse http://<vps>:6080 para fazer login no navegador."
            )

        logger.info("Navegação concluída — pronto para enviar mensagens.")

    async def _delete_current_gemini_conversation(self) -> None:
        """Deleta a conversa atual do Gemini para não ficar no histórico.

        Tenta clicar no menu de opções da conversa e depois em 'Excluir'.
        Falha silenciosa — se não conseguir deletar, apenas loga warning.
        """
        try:
            # Aguarda um momento para a conversa ser registrada
            await asyncio.sleep(1)

            # Seletores para o menu de opções da conversa ativa na sidebar
            menu_selectors = [
                'button[aria-label*="Mais opções"]',
                'button[aria-label*="More options"]',
                'button[aria-label*="Options"]',
                'button[data-test-id="conversation-options-button"]',
                'mat-icon[fonticon="more_vert"]',
            ]

            menu_clicked = False
            for sel in menu_selectors:
                try:
                    btn = self._page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        menu_clicked = True
                        logger.debug(f"Menu de conversa aberto via: {sel}")
                        break
                except Exception:
                    continue

            if not menu_clicked:
                logger.debug("Menu de opções da conversa não encontrado — pulando deleção")
                return

            await asyncio.sleep(0.5)

            # Seletores para o botão de deletar no menu
            delete_selectors = [
                'button:has-text("Excluir")',
                'button:has-text("Delete")',
                '[data-mat-icon-name="delete"]',
                'mat-icon[fonticon="delete"]',
            ]

            delete_clicked = False
            for sel in delete_selectors:
                try:
                    btn = self._page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        delete_clicked = True
                        logger.debug(f"Botão excluir clicado via: {sel}")
                        break
                except Exception:
                    continue

            if not delete_clicked:
                # Fechar menu sem deletar (pressiona Escape)
                await self._page.keyboard.press("Escape")
                logger.debug("Botão excluir não encontrado — menu fechado")
                return

            await asyncio.sleep(0.5)

            # Confirmar exclusão (dialog de confirmação)
            confirm_selectors = [
                'button:has-text("Excluir")',
                'button:has-text("Delete")',
                'button:has-text("Confirmar")',
                'button:has-text("Confirm")',
            ]
            for sel in confirm_selectors:
                try:
                    btn = self._page.locator(sel).last
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        logger.info("Conversa Gemini deletada com sucesso.")
                        return
                except Exception:
                    continue

            logger.debug("Dialog de confirmação não encontrado.")
        except Exception as e:
            logger.warning(f"Não foi possível deletar conversa do Gemini: {e}")

    async def switch_provider(self, provider: str) -> None:
        """Troca o provider dinamicamente.

        Para Gemini a navegação acontece em cada send_message (nova conversa).
        Para ChatGPT navega normalmente.
        """
        self.provider = provider
        self.selectors = PROVIDERS.get(provider, CHATGPT)
        if provider != "gemini":
            await self.navigate_to_chat()
        logger.info(f"Provider trocado para: {provider}")

    async def send_message(self, text: str) -> str:
        """Envia uma mensagem e aguarda a resposta completa da IA.

        Para Gemini, navega para uma nova conversa antes de enviar e deleta
        a conversa após receber a resposta (modo anônimo — sem histórico).
        """
        if self.provider == "gemini":
            await self.navigate_to_chat()

        await self._fill_input(text)
        await asyncio.sleep(0.5)
        await self._click_submit()
        await asyncio.sleep(1)
        await self._wait_response_done()
        response = await self._extract_response()
        cleaned = self._clean(response)

        # Deletar a conversa do histórico do Gemini
        if self.provider == "gemini":
            await self._delete_current_gemini_conversation()

        return cleaned

    async def _fill_input(self, text: str) -> None:
        """Localiza o campo de input e preenche com o texto."""
        for selector in self.selectors["input"]:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible(timeout=3000):
                    await locator.focus()
                    await locator.fill("")
                    await locator.fill(text)
                    logger.debug(f"Input preenchido via: {selector}")
                    return
            except Exception:
                continue
        raise RuntimeError("Não foi possível encontrar o campo de input da IA.")

    async def _click_submit(self) -> None:
        """Tenta clicar no botão de enviar. Fallback: pressiona Enter."""
        for selector in self.selectors["submit"]:
            try:
                btn = self._page.locator(selector).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    logger.debug(f"Submit clicado via: {selector}")
                    return
            except Exception:
                continue
        # Fallback: Enter
        logger.debug("Nenhum botão submit encontrado — usando Enter")
        await self._page.keyboard.press("Enter")

    async def _wait_response_done(self) -> None:
        """Aguarda a IA terminar de gerar a resposta."""
        # Estratégia 1: detectar botão "stop" aparecendo e sumindo
        for selector in self.selectors["stop"]:
            try:
                await self._page.wait_for_selector(
                    selector, state="visible", timeout=5000
                )
                logger.debug(f"Botão stop visível: {selector} — aguardando conclusão")
                await self._page.wait_for_selector(
                    selector, state="detached", timeout=180000
                )
                logger.debug("Botão stop desapareceu — resposta concluída")
                await asyncio.sleep(1)
                return
            except Exception:
                continue

        # Estratégia 2: polling de estabilização do DOM
        logger.debug("Stop button não detectado — usando polling de estabilização")
        last_text = ""
        stable_count = 0
        for _ in range(60):  # máx 30 segundos
            current = await self._extract_response()
            if current and current == last_text:
                stable_count += 1
            else:
                stable_count = 0
            last_text = current
            if stable_count >= 3:
                logger.debug("Resposta estabilizou")
                return
            await asyncio.sleep(0.5)

        logger.warning("Timeout de estabilização — usando última resposta capturada")

    async def _extract_response(self) -> str:
        """Extrai o texto da última resposta da IA."""
        for selector in self.selectors["response"]:
            try:
                locator = self._page.locator(selector).last
                if await locator.is_visible(timeout=2000):
                    text = await locator.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue
        return ""

    async def _needs_login(self) -> bool:
        """Verifica se a página está pedindo login."""
        for selector in LOGIN_INDICATORS:
            try:
                locator = self._page.locator(selector).first
                if await locator.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
        return False

    def _clean(self, text: str) -> str:
        """Remove lixo de UI da resposta extraída."""
        for g in GARBAGE:
            if g in text:
                text = text.split(g)[0]
        return text.strip()

    def is_rate_limited(self, response: str) -> bool:
        """Detecta se a IA retornou erro de rate limit."""
        lower = response.lower()
        return any(phrase in lower for phrase in RATE_LIMIT_PHRASES)

    async def close(self) -> None:
        """Fecha o navegador e o Playwright."""
        try:
            if self._context:
                await self._context.close()
            if self._playwright:
                await self._playwright.stop()
            logger.info("Browser fechado.")
        except Exception as e:
            logger.warning(f"Erro ao fechar browser: {e}")
