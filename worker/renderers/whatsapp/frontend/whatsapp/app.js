/**
 * WhatsApp Clone - JavaScript
 * Lógica de renderização de mensagens e controle frame-a-frame
 * para captura pelo Playwright.
 */

(function () {
    'use strict';

    // ── Estado global ──
    let conversationData = null;
    let messagesContainer = null;
    let messagesInner = null;
    let typingIndicator = null;
    let statusBarTimeEl = null;
    let messageElements = [];

    // ── SVG Icons ──
    const ICONS = {
        back: '<svg viewBox="0 0 24 24"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>',
        videoCall: '<svg viewBox="0 0 24 24"><path d="M17 10.5V7c0-.55-.45-1-1-1H4c-.55 0-1 .45-1 1v10c0 .55.45 1 1 1h12c.55 0 1-.45 1-1v-3.5l4 4v-11l-4 4z"/></svg>',
        call: '<svg viewBox="0 0 24 24"><path d="M20.01 15.38c-1.23 0-2.42-.2-3.53-.56-.35-.12-.74-.03-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z"/></svg>',
        more: '<svg viewBox="0 0 24 24"><path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"/></svg>',
        emoji: '<svg viewBox="0 0 24 24"><path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"/></svg>',
        attach: '<svg viewBox="0 0 24 24"><path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/></svg>',
        camera: '<svg viewBox="0 0 24 24"><path d="M12 15.2c1.77 0 3.2-1.43 3.2-3.2S13.77 8.8 12 8.8 8.8 10.23 8.8 12s1.43 3.2 3.2 3.2zM9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9z"/></svg>',
        mic: '<svg viewBox="0 0 24 24"><path d="M12 14c1.66 0 2.99-1.34 2.99-3L15 5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"/></svg>',
        play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
        signal: '<svg viewBox="0 0 24 24"><rect x="2" y="16" width="3" height="5" rx="0.5"/><rect x="7" y="12" width="3" height="9" rx="0.5"/><rect x="12" y="8" width="3" height="13" rx="0.5"/><rect x="17" y="4" width="3" height="17" rx="0.5"/></svg>',
        wifi: '<svg viewBox="0 0 24 24"><path d="M1 9l2 2c4.97-4.97 13.03-4.97 18 0l2-2C16.93 2.93 7.08 2.93 1 9zm8 8l3 3 3-3c-1.65-1.66-4.34-1.66-6 0zm-4-4l2 2c2.76-2.76 7.24-2.76 10 0l2-2C15.14 9.14 8.87 9.14 5 13z"/></svg>',
        battery: '<svg viewBox="0 0 24 24"><path d="M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4z"/></svg>',
        tickSingle: '<svg viewBox="0 0 16 11"><path d="M11.071.653a.457.457 0 00-.304-.102.493.493 0 00-.381.178l-6.19 7.636-2.011-2.095a.434.434 0 00-.329-.139c-.138 0-.271.057-.375.157l-.633.672a.607.607 0 00-.14.395c0 .163.058.308.157.408l3.01 3.135c.108.112.255.173.39.173.166 0 .341-.08.459-.248L11.461 1.4a.48.48 0 00.107-.322.508.508 0 00-.157-.362l-.34-.063z"/></svg>',
        tickDouble: '<svg viewBox="0 0 16 11"><path d="M11.071.653a.457.457 0 00-.304-.102.493.493 0 00-.381.178l-6.19 7.636-2.011-2.095a.434.434 0 00-.329-.139c-.138 0-.271.057-.375.157l-.633.672a.607.607 0 00-.14.395c0 .163.058.308.157.408l3.01 3.135c.108.112.255.173.39.173.166 0 .341-.08.459-.248L11.461 1.4a.48.48 0 00.107-.322.508.508 0 00-.157-.362l-.34-.063z"/><path d="M15.071.653a.457.457 0 00-.304-.102.493.493 0 00-.381.178l-6.19 7.636-1.143-1.191-.459.6 1.233 1.284c.108.112.255.173.39.173.166 0 .341-.08.459-.248L15.461 1.4a.48.48 0 00.107-.322.508.508 0 00-.157-.362l-.34-.063z"/></svg>',
    };

    // ── Gerador de avatar padrão ──
    function generateDefaultAvatar() {
        return 'data:image/svg+xml,' + encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">' +
            '<rect width="200" height="200" fill="#DFE5E7"/>' +
            '<circle cx="100" cy="80" r="35" fill="#C8D1D6"/>' +
            '<ellipse cx="100" cy="170" rx="55" ry="45" fill="#C8D1D6"/>' +
            '</svg>'
        );
    }

    // ── Gerar waveform aleatório para áudio ──
    function generateWaveformBars() {
        const bars = [];
        for (let i = 0; i < 28; i++) {
            const h = 4 + Math.random() * 24;
            bars.push(`<span class="bar" style="height:${h}px"></span>`);
        }
        return bars.join('');
    }

    // ── Criar tick SVG ──
    function createTickSvg(status) {
        if (status === 'read') {
            return `<span class="message-ticks">${ICONS.tickDouble.replace('<svg', '<svg class="tick-read"')}</span>`;
        } else if (status === 'delivered') {
            return `<span class="message-ticks">${ICONS.tickDouble.replace('<svg', '<svg class="tick-delivered"')}</span>`;
        } else if (status === 'sent') {
            return `<span class="message-ticks">${ICONS.tickSingle.replace('<svg', '<svg class="tick-sent"')}</span>`;
        }
        return '';
    }

    // ── Criar elemento de mensagem ──
    function createMessageElement(msg, index) {
        // Separador de data
        if (msg.type === 'date_separator') {
            const el = document.createElement('div');
            el.className = 'date-separator';
            el.id = `msg-${index}`;
            el.innerHTML = `<span class="date-separator-label">${escapeHtml(msg.text || '')}</span>`;
            return el;
        }

        const isSent = msg.sender === 'me';
        const el = document.createElement('div');
        el.className = `message ${isSent ? 'sent' : 'received'}`;
        el.id = `msg-${index}`;

        let bubbleContent = '';

        // Imagem
        if (msg.type === 'image') {
            const imgSrc = msg.media_uri || msg.media_path || '';
            if (imgSrc) {
                bubbleContent += `<div class="message-image"><img src="${imgSrc}" alt="foto" loading="eager" /></div>`;
            }
            if (msg.text) {
                bubbleContent += `<div class="message-text">${escapeHtml(msg.text)}</div>`;
            }
        }
        // Áudio
        else if (msg.type === 'audio') {
            bubbleContent += `
                <div class="message-audio">
                    <div class="audio-play-btn">${ICONS.play}</div>
                    <div class="audio-waveform">${generateWaveformBars()}</div>
                    <span class="audio-duration">0:15</span>
                </div>`;
        }
        // Emoji grande
        else if (msg.type === 'emoji') {
            bubbleContent += `<div class="message-emoji">${msg.text || ''}</div>`;
        }
        // Texto normal
        else {
            bubbleContent += `<div class="message-text">${formatText(msg.text || '')}</div>`;
        }

        // Meta (hora + ticks)
        const ticks = isSent ? createTickSvg(msg.status || 'read') : '';
        bubbleContent += `
            <div class="message-meta">
                <span class="message-time">${escapeHtml(msg.time || '')}</span>
                ${ticks}
            </div>`;

        el.innerHTML = `<div class="message-bubble">${bubbleContent}</div>`;
        return el;
    }

    // ── Escape HTML ──
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Formatar texto (emojis, links, etc.) ──
    function formatText(text) {
        // Escape HTML first
        let formatted = escapeHtml(text);
        // Negrito: *texto*
        formatted = formatted.replace(/\*([^*]+)\*/g, '<strong>$1</strong>');
        // Itálico: _texto_
        formatted = formatted.replace(/_([^_]+)_/g, '<em>$1</em>');
        // Riscado: ~texto~
        formatted = formatted.replace(/~([^~]+)~/g, '<del>$1</del>');
        return formatted;
    }

    // ═══════════════════════════════════════════════════════
    // API pública chamada pelo Playwright
    // ═══════════════════════════════════════════════════════

    /**
     * Inicializa a conversa com dados JSON.
     * Chamada uma vez antes de começar a renderização.
     */
    window.initConversation = function (data) {
        conversationData = data;

        // Referências do DOM
        messagesContainer = document.getElementById('chat-messages');
        messagesInner = document.getElementById('messages-inner');
        typingIndicator = document.getElementById('typing-indicator');
        statusBarTimeEl = document.getElementById('status-bar-time');

        // Configurar header
        const nameEl = document.getElementById('contact-name');
        const statusEl = document.getElementById('contact-status');
        const avatarEl = document.getElementById('contact-avatar');

        if (nameEl) nameEl.textContent = data.contact_name || 'Contato';
        if (statusEl) statusEl.textContent = data.contact_status || 'online';
        if (avatarEl) {
            avatarEl.src = data.contact_photo || generateDefaultAvatar();
        }

        // Wallpaper ou cor de fundo
        if (data.wallpaper) {
            messagesContainer.classList.add('has-wallpaper');
            const wpBg = document.createElement('div');
            wpBg.className = 'wallpaper-bg';
            wpBg.style.backgroundImage = `url(${data.wallpaper})`;
            messagesContainer.insertBefore(wpBg, messagesContainer.firstChild);
        } else if (data.bg_color) {
            messagesContainer.style.backgroundImage = 'none';
            messagesContainer.style.backgroundColor = data.bg_color;
        }

        // Cores customizadas
        if (data.sent_color) {
            document.documentElement.style.setProperty('--wa-sent-bg', data.sent_color);
        }
        if (data.received_color) {
            document.documentElement.style.setProperty('--wa-received-bg', data.received_color);
        }

        // Renderizar todas as mensagens (inicialmente ocultas)
        messageElements = [];
        if (messagesInner) {
            messagesInner.innerHTML = '';
            (data.messages || []).forEach(function (msg, idx) {
                const el = createMessageElement(msg, idx);
                messagesInner.appendChild(el);
                messageElements.push(el);
            });
        }

        // Adicionar indicador de digitação
        if (typingIndicator) {
            messagesInner.appendChild(typingIndicator);
        }
    };

    /**
     * Renderiza um frame específico.
     * Chamada pelo Playwright para cada frame do vídeo.
     *
     * @param {Object} state - Estado do frame
     * @param {number} state.scrollY - Posição de scroll
     * @param {number[]} state.visibleMessages - Índices de mensagens visíveis
     * @param {Object} state.messageOpacity - Mapa índice → opacidade (0-1)
     * @param {Object} state.messageTranslateY - Mapa índice → translateY em px
     * @param {boolean} state.showTyping - Mostrar indicador de digitação
     * @param {string} state.statusBarTime - Hora na status bar
     */
    window.renderFrame = function (state) {
        if (!messagesInner) return;

        // Atualizar hora na status bar
        if (statusBarTimeEl && state.statusBarTime) {
            statusBarTimeEl.textContent = state.statusBarTime;
        }

        // Aplicar visibilidade e animação em cada mensagem
        for (let i = 0; i < messageElements.length; i++) {
            const el = messageElements[i];
            const isVisible = state.visibleMessages.indexOf(i) !== -1;

            if (isVisible) {
                const opacity = state.messageOpacity[String(i)];
                const translateY = state.messageTranslateY[String(i)] || 0;

                el.classList.add('visible');
                if (opacity !== undefined && opacity < 1) {
                    el.style.opacity = opacity;
                    el.style.transform = translateY ? `translateY(${translateY}px)` : '';
                } else {
                    el.style.opacity = '1';
                    el.style.transform = '';
                }
            } else {
                el.classList.remove('visible');
                el.style.opacity = '0';
            }
        }

        // Indicador de digitação
        if (typingIndicator) {
            if (state.showTyping) {
                typingIndicator.classList.add('active');
            } else {
                typingIndicator.classList.remove('active');
            }
        }

        // Scroll
        if (messagesInner) {
            messagesInner.style.transform = `translateY(${-state.scrollY}px)`;
        }
    };

})();
