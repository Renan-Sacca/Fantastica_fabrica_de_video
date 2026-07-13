/**
 * Vídeo Compositor — Lógica do editor visual v2
 * Suporta: múltiplos áudios, OmniVoice com seleção de voz/preset/configuração,
 *          imagens de fundo por segmento de tempo, imagens sobrepostas por segmento.
 */

// ══════════════════════════════════════════
// Estado global
// ══════════════════════════════════════════
const state = {
    selectedAnimations: [],
    selectedElements: [],
    layers: [],
    resolution: '1080x1920',
    audioItems: [],       // [{type:'upload'|'omni', file:File|null, omni:{...}, volume:100}]
    bgSegments: [],       // [{file:File, previewUrl:str, startSec:num, endSec:num|null}]
    overlaySegments: [],  // [{file:File, previewUrl:str, startSec:num, endSec:num|null, position:str, scale:num}]
    jobId: null,
    eventSource: null,
    // OmniVoice shared data
    omniVoices: [],
    omniPresets: [],
    // Timeline de preview
    totalDuration: 0,      // duração total calculada a partir dos áudios (considerando corte)
};

let audioItemCounter = 0;
let bgSegmentCounter = 0;
let overlaySegmentCounter = 0;

// ══════════════════════════════════════════
// Resolução
// ══════════════════════════════════════════
function selectResolution(btn) {
    document.querySelectorAll('.res-chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    state.resolution = btn.dataset.res;
    document.getElementById('resolution').value = state.resolution;
    const canvas = document.getElementById('previewCanvas');
    const [w, h] = state.resolution.split('x').map(Number);
    canvas.style.aspectRatio = `${w}/${h}`;
    // Resolução muda os cálculos px do controle fino de overlays
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach(_syncFineFromQuick);
    refreshPreviewNow();
}

// ══════════════════════════════════════════
// Volume display
// ══════════════════════════════════════════
function updateVolDisplay(input, spanId) {
    document.getElementById(spanId).textContent = `${input.value}%`;
}

// ══════════════════════════════════════════
// Accordion
// ══════════════════════════════════════════
function toggleSection(header) {
    const body = header.nextElementSibling;
    header.classList.toggle('collapsed');
    body.classList.toggle('collapsed');
}

// ══════════════════════════════════════════
// OmniVoice: carregar vozes e presets compartilhados
// ══════════════════════════════════════════
async function loadOmniVoices() {
    try {
        const res = await fetch('/audio/api/voices');
        if (!res.ok) return;
        const data = await res.json();
        state.omniVoices = data.custom || [];
        refreshAllVoiceSelects();
    } catch (e) { /* silencioso */ }
}

async function loadOmniPresets() {
    try {
        const res = await fetch('/audio/api/presets');
        if (!res.ok) return;
        const data = await res.json();
        state.omniPresets = data.presets || [];
        refreshAllPresetSelects();
    } catch (e) { /* silencioso */ }
}

function refreshAllVoiceSelects() {
    document.querySelectorAll('.omni-voice-select').forEach(sel => {
        const current = sel.value;
        if (state.omniVoices.length) {
            sel.innerHTML = state.omniVoices
                .map(v => `<option value="${v.id}"${v.id === current ? ' selected' : ''}>${v.name}</option>`)
                .join('');
        } else {
            sel.innerHTML = '<option value="">Nenhuma voz — crie em Gerar Áudio</option>';
        }
    });
}

function refreshAllPresetSelects() {
    document.querySelectorAll('.omni-preset-select').forEach(sel => {
        const current = sel.value;
        sel.innerHTML = '<option value="">Selecione um preset...</option>' +
            state.omniPresets.map(p =>
                `<option value="${p.preset_id}"${p.preset_id === current ? ' selected' : ''}>${p.name}</option>`
            ).join('');
        sel.onchange = () => applyPresetToBlock(sel);
    });
}

function applyPresetToBlock(sel) {
    const presetId = sel.value;
    if (!presetId) return;
    const preset = state.omniPresets.find(p => p.preset_id === presetId);
    if (!preset || !preset.params) return;
    const block = sel.closest('.audio-panel');
    if (!block) return;
    const params = preset.params;
    ['num_step','guidance_scale','speed','language_id','position_temperature','class_temperature'].forEach(k => {
        const el = block.querySelector(`.omni-p.${k}`);
        if (el && params[k] != null) el.value = params[k];
    });
    const denoise = block.querySelector('.omni-p-denoise');
    const pre = block.querySelector('.omni-p-preprocess');
    const post = block.querySelector('.omni-p-postprocess');
    if (denoise && params.denoise != null) denoise.checked = !!params.denoise;
    if (pre && params.preprocess_prompt != null) pre.checked = !!params.preprocess_prompt;
    if (post && params.postprocess_output != null) post.checked = !!params.postprocess_output;
    showToast(`Preset "${preset.name}" aplicado!`, 'success');
}

// ══════════════════════════════════════════
// Áudio: OmniVoice mode toggle dentro de um item
// ══════════════════════════════════════════
function switchOmniMode(btn) {
    const block = btn.closest('.audio-panel');
    block.querySelectorAll('.omni-mode-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    const mode = btn.dataset.mode;
    block.querySelectorAll('.omni-sub-panel').forEach(p => {
        p.style.display = p.dataset.sub === mode ? 'block' : 'none';
    });
}

// ══════════════════════════════════════════
// Áudio: Adicionar/Remover itens
// ══════════════════════════════════════════
function addAudioItem() {
    audioItemCounter++;
    const idx = audioItemCounter;
    const container = document.getElementById('audioItemsList');

    const wrapper = document.createElement('div');
    wrapper.className = 'audio-item';
    wrapper.dataset.idx = idx;
    // Estado do áudio IA pré-gerado
    wrapper._omniGenerated = null; // {job_id, audio_url, blob}
    wrapper._omniEventSource = null;

    wrapper.innerHTML = `
        <div class="audio-item-header">
            <div class="audio-item-num">${container.querySelectorAll('.audio-item').length + 1}</div>
            <span class="audio-item-title">Áudio ${container.querySelectorAll('.audio-item').length + 1}</span>
            <div style="display:flex; gap:6px;">
                <div class="audio-tabs" style="margin:0;">
                    <button type="button" class="audio-tab active" onclick="switchAudioType(this,'upload')">📁 Arquivo</button>
                    <button type="button" class="audio-tab" onclick="switchAudioType(this,'omni')">🤖 IA</button>
                </div>
                <button type="button" class="audio-item-remove" onclick="removeAudioItem(this)" title="Remover áudio">✕</button>
            </div>
        </div>
        <div class="audio-panels-wrap"></div>
    `;

    const panelsWrap = wrapper.querySelector('.audio-panels-wrap');

    // Upload panel
    const uploadTpl = document.getElementById('tplAudioUpload').content.cloneNode(true);
    panelsWrap.appendChild(uploadTpl);

    // Omni panel
    const omniTpl = document.getElementById('tplAudioOmni').content.cloneNode(true);
    const omniPanel = omniTpl.querySelector('.audio-panel');
    omniPanel.classList.remove('active');
    panelsWrap.appendChild(omniTpl);

    container.appendChild(wrapper);

    // Setup file input for upload panel — com player de preview
    const fileInput = wrapper.querySelector('.audio-file-input');
    const fileName = wrapper.querySelector('.audio-panel[data-panel-type=upload] .file-name');
    const uploadPanel = wrapper.querySelector('.audio-panel[data-panel-type=upload]');
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            fileName.textContent = '✅ ' + fileInput.files[0].name;
            fileName.style.display = 'block';
            // Criar preview de áudio
            setupAudioPreviewFromFile(uploadPanel, fileInput.files[0]);
        }
        updateAudioPreview();
    });

    // Volume display for all range inputs in this item
    wrapper.querySelectorAll('.audio-vol-range').forEach(range => {
        range.addEventListener('input', () => {
            range.nextElementSibling.textContent = range.value + '%';
        });
    });

    // Populate voice/preset selects
    const voiceSel = wrapper.querySelector('.omni-voice-select');
    if (state.omniVoices.length) {
        voiceSel.innerHTML = state.omniVoices.map(v => `<option value="${v.id}">${v.name}</option>`).join('');
    } else {
        voiceSel.innerHTML = '<option value="">Nenhuma voz — crie em Gerar Áudio</option>';
    }

    const presetSel = wrapper.querySelector('.omni-preset-select');
    presetSel.innerHTML = '<option value="">Selecione um preset...</option>' +
        state.omniPresets.map(p => `<option value="${p.preset_id}">${p.name}</option>`).join('');
    presetSel.addEventListener('change', () => applyPresetToBlock(presetSel));

    renumberAudioItems();
    updateAudioPreview();
    updateLayers();
}

function switchAudioType(btn, type) {
    const item = btn.closest('.audio-item');
    item.querySelectorAll('.audio-item-header .audio-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    item.querySelectorAll('.audio-panel').forEach(p => {
        p.classList.toggle('active', p.dataset.panelType === type);
    });
    refreshTimelineUI();
}

function removeAudioItem(btn) {
    const item = btn.closest('.audio-item');
    // Fechar EventSource se existir
    if (item._omniEventSource) {
        item._omniEventSource.close();
        item._omniEventSource = null;
    }
    // Revogar ObjectURL se existir
    const audioEl = item.querySelector('.audio-preview-el');
    if (audioEl && audioEl.src && audioEl.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioEl.src);
    }
    item.remove();
    renumberAudioItems();
    updateAudioPreview();
    updateLayers();
    refreshTimelineUI();
}

function renumberAudioItems() {
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        item.querySelector('.audio-item-num').textContent = i + 1;
        item.querySelector('.audio-item-title').textContent = `Áudio ${i + 1}`;
    });
}

function updateAudioPreview() {
    const count = document.querySelectorAll('#audioItemsList .audio-item').length;
    document.getElementById('previewAudioCount').textContent =
        count === 0 ? '—' : `${count} áudio${count > 1 ? 's' : ''} configurado${count > 1 ? 's' : ''}`;
}

// ══════════════════════════════════════════
// Imagens de Fundo: Adicionar/Remover
// ══════════════════════════════════════════
function addBgSegment() {
    bgSegmentCounter++;
    const container = document.getElementById('bgSegmentsList');
    const tpl = document.getElementById('tplBgSegment').content.cloneNode(true);
    const seg = tpl.querySelector('.img-segment');
    seg.dataset.bgIdx = bgSegmentCounter;

    container.appendChild(tpl);

    const added = container.querySelector(`[data-bg-idx="${bgSegmentCounter}"]`);
    setupImageSegment(added, 'bg');
    renumberBgSegments();
    updateLayers();
    refreshTimelineUI();
}

function removeBgSegment(btn) {
    btn.closest('.img-segment').remove();
    renumberBgSegments();
    updateLayers();
    refreshTimelineUI();
}

function renumberBgSegments() {
    document.querySelectorAll('#bgSegmentsList .img-segment').forEach((seg, i) => {
        seg.querySelector('.img-segment-num').textContent = i + 1;
    });
}

// ══════════════════════════════════════════
// Imagens Sobrepostas: Adicionar/Remover
// ══════════════════════════════════════════
function addOverlaySegment() {
    overlaySegmentCounter++;
    const container = document.getElementById('overlaySegmentsList');
    const tpl = document.getElementById('tplOverlaySegment').content.cloneNode(true);
    const seg = tpl.querySelector('.img-segment');
    seg.dataset.ovIdx = overlaySegmentCounter;

    container.appendChild(tpl);

    const added = container.querySelector(`[data-ov-idx="${overlaySegmentCounter}"]`);
    setupImageSegment(added, 'overlay');

    // Atualiza preview ao mudar posição ou escala, e sincroniza campos px
    added.querySelectorAll('.overlay-pos-grid button').forEach(btn => {
        btn.addEventListener('click', () => refreshPreviewNow());
    });
    const scaleRange = added.querySelector('.overlay-scale-range');
    if (scaleRange) {
        scaleRange.addEventListener('input', () => {
            scaleRange.nextElementSibling.textContent = scaleRange.value + '%';
            _syncFineFromQuick(added);
            refreshPreviewNow();
        });
    }

    renumberOverlaySegments();
    updateLayers();
    refreshTimelineUI();
}

function removeOverlaySegment(btn) {
    btn.closest('.img-segment').remove();
    renumberOverlaySegments();
    updateLayers();
    refreshTimelineUI();
}

function renumberOverlaySegments() {
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach((seg, i) => {
        seg.querySelector('.img-segment-num').textContent = i + 1;
    });
}

// ══════════════════════════════════════════
// Posição da imagem sobreposta dentro de um segmento
// ══════════════════════════════════════════

/**
 * Converte escala % → largura/altura em pixels de saída,
 * respeitando a proporção da imagem se já estiver carregada.
 */
function _scaleToPx(seg, scalePercent) {
    const [outW, outH] = state.resolution.split('x').map(Number);
    const imgEl = seg.querySelector('.preview');
    const hasImg = imgEl && imgEl.naturalWidth > 0;

    let w, h;
    if (hasImg) {
        const ratio = imgEl.naturalWidth / imgEl.naturalHeight;
        // Usa a largura de saída como 100%
        w = Math.round(outW * scalePercent / 100);
        h = Math.round(w / ratio);
        // Se ultrapassar a altura, limita pela altura
        if (h > outH) {
            h = Math.round(outH * scalePercent / 100);
            w = Math.round(h * ratio);
        }
    } else {
        // Sem imagem: escala baseada apenas na largura de saída
        w = Math.round(outW * scalePercent / 100);
        h = null; // não preenche altura sem saber o ratio
    }
    return { w, h };
}

/**
 * Converte posição semântica + dimensões → X, Y em pixels (canto superior-esquerdo da imagem).
 */
function _posToPx(posKey, imgW, imgH) {
    const [outW, outH] = state.resolution.split('x').map(Number);
    const w = imgW || 0;
    const h = imgH || 0;
    const pad = Math.round(outW * 0.05); // 5% de padding lateral

    const map = {
        'centro':            { x: Math.round((outW - w) / 2),          y: Math.round((outH - h) / 2) },
        'superior':          { x: Math.round((outW - w) / 2),          y: pad },
        'inferior':          { x: Math.round((outW - w) / 2),          y: outH - h - pad },
        'esquerda':          { x: pad,                                  y: Math.round((outH - h) / 2) },
        'direita':           { x: outW - w - pad,                       y: Math.round((outH - h) / 2) },
        'superior esquerda': { x: pad,                                  y: pad },
        'superior direita':  { x: outW - w - pad,                       y: pad },
        'inferior esquerda': { x: pad,                                  y: outH - h - pad },
        'inferior direita':  { x: outW - w - pad,                       y: outH - h - pad },
    };
    return map[posKey] || map['centro'];
}

/** Preenche os campos px do controle fino a partir dos controles rápidos. */
function _syncFineFromQuick(seg) {
    const scaleRange = seg.querySelector('.overlay-scale-range');
    const activePos  = seg.querySelector('.overlay-pos-grid button.active');
    if (!scaleRange || !activePos) return;

    const scale  = parseInt(scaleRange.value);
    const posKey = activePos.dataset.pos || 'centro';
    const { w, h } = _scaleToPx(seg, scale);
    const { x, y } = _posToPx(posKey, w, h || 0);

    const pxW = seg.querySelector('.overlay-px-w');
    const pxH = seg.querySelector('.overlay-px-h');
    const pxX = seg.querySelector('.overlay-px-x');
    const pxY = seg.querySelector('.overlay-px-y');

    if (pxW) pxW.value = w;
    if (pxH && h !== null) pxH.value = h;
    if (pxX) pxX.value = x;
    if (pxY) pxY.value = y;
}

function selectOvPos(btn) {
    const grid = btn.closest('.overlay-pos-grid');
    grid.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const seg = btn.closest('.img-segment');
    if (seg) _syncFineFromQuick(seg);
    refreshPreviewNow();
}

// ══════════════════════════════════════════
// Controle fino: aplica tamanho/posição px ao preview
/**
 * Aplica tamanho/posição em pixels (resolução de saída) a um elemento de
 * overlay já criado no preview, convertendo para a escala do canvas atual.
 */
function applyFinePositionToEl(overlayEl, pxW, pxH, pxX, pxY) {
    const canvas = document.getElementById('previewCanvas');
    const canvasRect = canvas.getBoundingClientRect();
    const [outW, outH] = state.resolution.split('x').map(Number);
    const scaleX = canvasRect.width / outW;
    const scaleY = canvasRect.height / outH;

    // Reseta todos os posicionamentos
    overlayEl.style.top = 'auto';
    overlayEl.style.left = 'auto';
    overlayEl.style.right = 'auto';
    overlayEl.style.bottom = 'auto';
    overlayEl.style.transform = 'none';
    overlayEl.style.maxWidth = 'none';
    overlayEl.style.maxHeight = 'none';
    overlayEl.style.width = 'auto';
    overlayEl.style.height = 'auto';

    if (pxW) overlayEl.style.width = `${parseFloat(pxW) * scaleX}px`;
    if (pxH) overlayEl.style.height = `${parseFloat(pxH) * scaleY}px`;

    if (pxX !== '' && pxX !== undefined) {
        overlayEl.style.left = `${parseFloat(pxX) * scaleX}px`;
    } else {
        overlayEl.style.left = '50%';
        overlayEl.style.transform = overlayEl.style.transform === 'none'
            ? 'translateX(-50%)' : overlayEl.style.transform;
    }
    if (pxY !== '' && pxY !== undefined) {
        overlayEl.style.top = `${parseFloat(pxY) * scaleY}px`;
    } else {
        overlayEl.style.top = '50%';
        if (overlayEl.style.left === '50%') {
            overlayEl.style.transform = 'translate(-50%,-50%)';
        } else {
            overlayEl.style.transform = 'translateY(-50%)';
        }
    }
}

/** Botão "Aplicar ao preview" do controle fino — apenas força um redraw do preview. */
function applyFinePosition(btn) {
    const seg = btn.closest('.img-segment');
    if (!seg) return;

    const fileInput = seg.querySelector('.overlay-img-input');
    if (!fileInput?.files[0]) {
        showToast('Adicione uma imagem sobreposta primeiro.', 'error');
        return;
    }

    refreshPreviewNow();
    showToast('Preview atualizado!', 'success');
}

// ══════════════════════════════════════════
// Setup genérico de segmento de imagem (file input + preview + time)
// ══════════════════════════════════════════
function setupImageSegment(seg, type) {
    const fileInput = seg.querySelector(`input[type=file]`);
    const preview = seg.querySelector('.preview');
    const fileName = seg.querySelector('.file-name');

    fileInput.addEventListener('change', () => {
        const file = fileInput.files[0];
        if (!file) return;
        fileName.textContent = '✅ ' + file.name;
        fileName.style.display = 'block';
        const reader = new FileReader();
        reader.onload = ev => {
            preview.src = ev.target.result;
            preview.style.display = 'block';
            if (type === 'bg') {
                refreshPreviewNow();
            } else if (type === 'overlay') {
                // Espera o elemento carregar para ter naturalWidth/Height
                preview.onload = () => {
                    _syncFineFromQuick(seg);
                    refreshPreviewNow();
                };
            }
        };
        reader.readAsDataURL(file);
        updateLayers();
    });

    // Campos de início/fim: aplica limite (clamp) na duração total e atualiza a timeline
    const startInput = seg.querySelector('.seg-start');
    const endInput = seg.querySelector('.seg-end');
    [startInput, endInput].forEach(el => {
        if (!el) return;
        el.addEventListener('input', () => checkSegmentTimeWarning(seg));
        el.addEventListener('change', () => {
            clampSegmentTimes(seg);
            refreshPreviewNow();
        });
        el.addEventListener('blur', () => {
            clampSegmentTimes(seg);
            refreshPreviewNow();
        });
    });
}

// ══════════════════════════════════════════
// Duração total dos áudios (considerando corte/trim)
// ══════════════════════════════════════════

/** Duração efetiva de um item de áudio, aplicando trim_start/trim_end se definidos. */
function getAudioItemEffectiveDuration(item) {
    const activePanel = item.querySelector('.audio-panel.active');
    if (!activePanel) return 0;
    const audioEl = activePanel.querySelector('.audio-preview-el');
    const rawDuration = audioEl && isFinite(audioEl.duration) ? audioEl.duration : 0;
    if (!rawDuration) return 0;

    const trimStartRaw = activePanel.querySelector('.trim-start')?.value.trim();
    const trimEndRaw = activePanel.querySelector('.trim-end')?.value.trim();
    const trimStart = trimStartRaw ? Math.max(0, parseFloat(trimStartRaw)) : 0;
    const trimEnd = trimEndRaw ? Math.min(rawDuration, parseFloat(trimEndRaw)) : rawDuration;

    return Math.max(0, trimEnd - trimStart);
}

/** Soma a duração efetiva de todos os áudios principais (eles são concatenados). */
function computeTotalDuration() {
    let total = 0;
    document.querySelectorAll('#audioItemsList .audio-item').forEach(item => {
        total += getAudioItemEffectiveDuration(item);
    });
    state.totalDuration = total;
    return total;
}

/** Lê start/end (segundos) de todos os segmentos de fundo, na ordem do DOM. */
function getBgSegmentsData() {
    return Array.from(document.querySelectorAll('#bgSegmentsList .img-segment')).map(seg => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        const start = startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0;
        const endRaw = endInput ? endInput.value.trim() : '';
        const end = endRaw !== '' ? parseFloat(endRaw) : null;
        return { seg, start, end };
    });
}

/** Lê start/end (segundos) de todos os segmentos sobrepostos, na ordem do DOM. */
function getOverlaySegmentsData() {
    return Array.from(document.querySelectorAll('#overlaySegmentsList .img-segment')).map(seg => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        const start = startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0;
        const endRaw = endInput ? endInput.value.trim() : '';
        const end = endRaw !== '' ? parseFloat(endRaw) : null;
        return { seg, start, end };
    });
}

/**
 * Encontra o segmento ativo num instante t (segundos).
 *
 * @param {boolean} allowGapFill - Se true (fundo), preenche lacunas usando o
 *   último segmento que já começou, mesmo passado seu próprio fim (o fundo
 *   deve sempre mostrar algo). Se false (sobreposta), a busca é estrita: fora
 *   da própria janela [start, end) o segmento não é considerado — retorna
 *   null quando nada cobre o instante t.
 */
function findActiveSegmentAtTime(segments, t, allowGapFill = true) {
    if (!segments.length) return null;
    const candidates = segments.filter(s => s.start <= t && (s.end === null || t < s.end));
    if (candidates.length) {
        // Em caso de sobreposição, prioriza o que começou mais recentemente
        return candidates.reduce((a, b) => (b.start >= a.start ? b : a));
    }
    if (!allowGapFill) return null;

    // Sem correspondência exata: usa o último que já começou (cobre gaps) — só para o fundo
    const before = segments.filter(s => s.start <= t);
    if (before.length) {
        return before.reduce((a, b) => (b.start >= a.start ? b : a));
    }
    // t é anterior a todos os segmentos: usa o primeiro
    return segments.reduce((a, b) => (b.start <= a.start ? b : a));
}

/** Mostra qual(is) imagem(ns) está(ão) ativa(s) no instante atual, na área de status da timeline. */
function updateTimelineStatusLabel(activeBg, activeOvList) {
    const statusEl = document.getElementById('previewTimeStatus');
    if (!statusEl) return;
    if (state.totalDuration <= 0) {
        statusEl.textContent = 'Adicione áudios para calcular a duração';
        return;
    }
    const allBg = Array.from(document.querySelectorAll('#bgSegmentsList .img-segment'));
    const allOv = Array.from(document.querySelectorAll('#overlaySegmentsList .img-segment'));
    const bgIdx = activeBg ? allBg.indexOf(activeBg.seg) + 1 : null;
    const parts = [];
    if (bgIdx) parts.push(`Fundo #${bgIdx}${allBg.length > 1 ? `/${allBg.length}` : ''}`);
    if (activeOvList && activeOvList.length) {
        const ovIdxs = activeOvList
            .map(ov => allOv.indexOf(ov.seg) + 1)
            .filter(i => i > 0)
            .sort((a, b) => a - b);
        if (ovIdxs.length) {
            parts.push(`Sobreposta${ovIdxs.length > 1 ? 's' : ''} #${ovIdxs.join(', #')}${allOv.length > 1 ? `/${allOv.length}` : ''}`);
        }
    }
    statusEl.textContent = parts.length ? parts.join(' · ') : 'Nenhuma imagem configurada para este momento';
}

/** Mostra aviso ao vivo (sem alterar valor) se início/fim ultrapassar a duração total. */
function checkSegmentTimeWarning(seg) {
    const warnMsg = seg.querySelector('.seg-time-warn-msg');
    const startInput = seg.querySelector('.seg-start');
    const endInput = seg.querySelector('.seg-end');
    if (!warnMsg) return;

    const total = state.totalDuration;
    const start = parseFloat(startInput?.value || '0') || 0;
    const endRaw = endInput?.value.trim();
    const end = endRaw ? parseFloat(endRaw) : null;

    let msg = '';
    if (total > 0 && start > total) {
        msg = `⚠️ Início maior que a duração total dos áudios (${total.toFixed(1)}s).`;
    } else if (total > 0 && end !== null && end > total) {
        msg = `⚠️ Fim maior que a duração total dos áudios (${total.toFixed(1)}s).`;
    } else if (end !== null && end <= start) {
        msg = '⚠️ O fim deve ser maior que o início.';
    }

    startInput?.classList.toggle('seg-time-warn', total > 0 && start > total);
    endInput?.classList.toggle('seg-time-warn', (total > 0 && end !== null && end > total) || (end !== null && end <= start));
    warnMsg.textContent = msg;
    warnMsg.classList.toggle('visible', !!msg);
}

/** Ajusta (corta) início/fim de um segmento para não passar da duração total. */
function clampSegmentTimes(seg) {
    const total = state.totalDuration;
    const startInput = seg.querySelector('.seg-start');
    const endInput = seg.querySelector('.seg-end');

    if (startInput) {
        let v = parseFloat(startInput.value || '0') || 0;
        if (v < 0) v = 0;
        if (total > 0 && v > total) v = total;
        startInput.value = v.toFixed(1);
    }
    if (endInput) {
        const raw = endInput.value.trim();
        if (raw !== '') {
            let v = parseFloat(raw);
            if (total > 0 && v > total) v = total;
            endInput.value = v.toFixed(1);
        }
    }
    checkSegmentTimeWarning(seg);
}

/** Recalcula duração total, ajusta limites dos segmentos e atualiza a UI da timeline. */
function refreshTimelineUI() {
    const total = computeTotalDuration();
    const slider = document.getElementById('previewTimeSlider');
    const totalLabel = document.getElementById('previewTotalDuration');
    const timeLabel = document.getElementById('previewTimeLabel');
    if (!slider) return;

    if (total > 0) {
        slider.disabled = false;
        slider.max = total.toFixed(1);
        if (parseFloat(slider.value) > total) slider.value = total.toFixed(1);
        totalLabel.textContent = `${total.toFixed(1)}s total`;
    } else {
        slider.disabled = true;
        slider.max = 0;
        slider.value = 0;
        totalLabel.textContent = '0.0s total';
    }
    timeLabel.textContent = `${(parseFloat(slider.value) || 0).toFixed(1)}s`;

    // Reajustar limites de todos os segmentos de fundo e sobrepostos
    document.querySelectorAll('#bgSegmentsList .img-segment').forEach(clampSegmentTimes);
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach(clampSegmentTimes);

    refreshPreviewNow();
}

/**
 * Encontra TODOS os segmentos ativos num instante t (busca estrita, sem
 * preenchimento de lacunas). Usado para overlays, que podem ter várias
 * imagens visíveis ao mesmo tempo (ex: uma de cada lado da tela).
 */
function findAllActiveSegmentsAtTime(segments, t) {
    return segments.filter(s => s.start <= t && (s.end === null || t < s.end));
}

/** Atualiza o preview visual com base no instante atual da timeline. */
function refreshPreviewNow() {
    const slider = document.getElementById('previewTimeSlider');
    const t = slider ? (parseFloat(slider.value) || 0) : 0;

    const bgSegs = getBgSegmentsData();
    const ovSegs = getOverlaySegmentsData();
    const activeBg = findActiveSegmentAtTime(bgSegs, t, true);
    const activeOvList = findAllActiveSegmentsAtTime(ovSegs, t);

    let bgUrl = null;
    if (activeBg) {
        const preview = activeBg.seg.querySelector('.preview');
        if (preview && preview.style.display !== 'none' && preview.src) bgUrl = preview.src;
    }

    // Monta lista de {url, seg} para cada overlay ativo no instante t
    const activeOverlays = activeOvList
        .map(ov => {
            const preview = ov.seg.querySelector('.preview');
            const url = preview && preview.style.display !== 'none' && preview.src ? preview.src : null;
            return url ? { url, seg: ov.seg } : null;
        })
        .filter(Boolean);

    updatePreview(bgUrl, activeOverlays);
    updateTimelineStatusLabel(activeBg, activeOvList);
}

// ══════════════════════════════════════════
// Preview
// ══════════════════════════════════════════
// Mapa de posição semântica → estilo CSS (usado no preview de overlays)
const OVERLAY_POS_MAP = {
    'centro':            { top:'50%',    left:'50%',   right:'auto', bottom:'auto', transform:'translate(-50%,-50%)' },
    'superior':          { top:'5%',     left:'50%',   right:'auto', bottom:'auto', transform:'translateX(-50%)' },
    'inferior':          { top:'auto',   left:'50%',   right:'auto', bottom:'5%',   transform:'translateX(-50%)' },
    'esquerda':          { top:'50%',    left:'5%',    right:'auto', bottom:'auto', transform:'translateY(-50%)' },
    'direita':           { top:'50%',    left:'auto',  right:'5%',   bottom:'auto', transform:'translateY(-50%)' },
    'superior esquerda': { top:'5%',     left:'5%',    right:'auto', bottom:'auto', transform:'none' },
    'superior direita':  { top:'5%',     left:'auto',  right:'5%',   bottom:'auto', transform:'none' },
    'inferior esquerda': { top:'auto',   left:'5%',    right:'auto', bottom:'5%',   transform:'none' },
    'inferior direita':  { top:'auto',   left:'auto',  right:'5%',   bottom:'5%',   transform:'none' },
};

/**
 * Atualiza o preview visual.
 * @param {string|null} bgUrl - URL da imagem de fundo ativa (ou null).
 * @param {Array<{url:string, seg:HTMLElement}>} activeOverlays - lista de
 *   overlays ativos no instante atual (pode ter 0, 1 ou mais itens).
 */
function updatePreview(bgUrl, activeOverlays) {
    const bgEl = document.getElementById('previewBg');
    const overlaysContainer = document.getElementById('previewOverlaysContainer');
    const placeholder = document.getElementById('previewPlaceholder');

    if (bgUrl) {
        bgEl.src = bgUrl;
        bgEl.style.display = 'block';
        placeholder.style.display = 'none';
    } else {
        bgEl.style.display = 'none';
        placeholder.style.display = 'flex';
    }

    overlaysContainer.innerHTML = '';
    (activeOverlays || []).forEach(({ url, seg }) => {
        const activePos = seg.querySelector('.overlay-pos-grid button.active');
        const scaleRange = seg.querySelector('.overlay-scale-range');
        const scale = scaleRange ? parseInt(scaleRange.value) : 50;
        const pos = activePos ? activePos.dataset.pos : 'centro';
        const p = OVERLAY_POS_MAP[pos] || OVERLAY_POS_MAP['centro'];

        const img = document.createElement('img');
        img.className = 'preview-overlay';
        img.src = url;
        img.alt = '';
        img.style.display = 'block';
        img.style.maxWidth = `${scale}%`;
        img.style.maxHeight = `${scale}%`;
        img.style.top = p.top;
        img.style.left = p.left;
        img.style.right = p.right;
        img.style.bottom = p.bottom;
        img.style.transform = p.transform;

        // Controle fino (px) tem prioridade sobre posição/escala rápida
        const pxW = seg.querySelector('.overlay-px-w')?.value.trim();
        const pxH = seg.querySelector('.overlay-px-h')?.value.trim();
        const pxX = seg.querySelector('.overlay-px-x')?.value.trim();
        const pxY = seg.querySelector('.overlay-px-y')?.value.trim();
        if (pxW || pxH || pxX !== '' || pxY !== '') {
            applyFinePositionToEl(img, pxW, pxH, pxX, pxY);
        }

        overlaysContainer.appendChild(img);
    });

    // Animações badges
    document.getElementById('previewAnimBadges').innerHTML = state.selectedAnimations
        .map(a => `<span>${getAnimName(a)}</span>`).join('');
}

function getAnimName(key) {
    const map = {
        particulas:'✨ Partículas', fumaca:'🌫️ Fumaça', brilho:'💎 Brilho',
        fogo:'🔥 Fogo', chuva:'🌧️ Chuva', neve:'❄️ Neve',
        faiscas:'⚡ Faíscas', explosao:'💥 Explosão', luz:'💡 Luz', loop_bg:'🔄 Loop'
    };
    return map[key] || key;
}

function getElemName(key) {
    const map = {
        moldura_gold:'🖼️ Moldura', moldura_neon:'💜 Neon', barra_inferior:'▬ Barra',
        caixa_texto:'💬 Caixa', gradiente_top:'🌅 Grad.Sup', gradiente_bottom:'🌆 Grad.Inf',
        sombra_vinheta:'🔲 Vinheta', sombra_radial:'⭕ Radial'
    };
    return map[key] || key;
}

// ══════════════════════════════════════════
// Gallery toggle
// ══════════════════════════════════════════
function toggleGalleryItem(el, type) {
    el.classList.toggle('selected');
    const value = el.getAttribute(type === 'animation' ? 'data-animation' : 'data-element');
    if (type === 'animation') {
        const idx = state.selectedAnimations.indexOf(value);
        if (idx >= 0) state.selectedAnimations.splice(idx, 1); else state.selectedAnimations.push(value);
    } else {
        const idx = state.selectedElements.indexOf(value);
        if (idx >= 0) state.selectedElements.splice(idx, 1); else state.selectedElements.push(value);
    }
    updateLayers();
    refreshPreviewNow();
}

// ══════════════════════════════════════════
// Camadas (drag & drop)
// ══════════════════════════════════════════
function updateLayers() {
    const list = [];
    const bgCount = document.querySelectorAll('#bgSegmentsList .img-segment').length;
    if (bgCount > 0) list.push({ id:'bg', icon:'🖼️', name:`Fundo (${bgCount} imagem${bgCount>1?'s':''})`, type:'background' });
    state.selectedElements.forEach(e => list.push({ id:`elem_${e}`, icon:'✨', name:getElemName(e), type:'element' }));
    state.selectedAnimations.forEach(a => list.push({ id:`anim_${a}`, icon:'🎬', name:getAnimName(a), type:'animation' }));
    const ovCount = document.querySelectorAll('#overlaySegmentsList .img-segment').length;
    if (ovCount > 0) list.push({ id:'overlay', icon:'📸', name:`Sobrepostas (${ovCount})`, type:'overlay' });
    state.layers = list;
    renderLayers();
}

function renderLayers() {
    const container = document.getElementById('layersList');
    if (!container) return;
    if (state.layers.length === 0) {
        container.innerHTML = `<div style="text-align:center; padding:20px; opacity:.5;"><span style="font-size:2rem; display:block; margin-bottom:8px;">📐</span><span style="font-size:.85rem;">Adicione elementos para ver as camadas</span></div>`;
        return;
    }
    container.innerHTML = state.layers.map((layer, i) => `
        <div class="layer-item" draggable="true"
             ondragstart="dragStart(event,${i})" ondragover="dragOver(event)"
             ondrop="dropLayer(event,${i})" ondragend="dragEnd(event)">
            <span class="layer-drag">⠿</span>
            <span style="font-size:1.1rem;">${layer.icon}</span>
            <span class="layer-name">${layer.name}</span>
            <span style="font-size:.65rem; opacity:.4; text-transform:uppercase;">${i===0?'TRÁS':i===state.layers.length-1?'FRENTE':''}</span>
        </div>`).join('');
}

let dragIdx = null;
function dragStart(e, idx) { dragIdx = idx; e.currentTarget.classList.add('dragging'); e.dataTransfer.effectAllowed = 'move'; }
function dragOver(e) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; }
function dropLayer(e, targetIdx) {
    e.preventDefault();
    if (dragIdx === null || dragIdx === targetIdx) return;
    const [item] = state.layers.splice(dragIdx, 1);
    state.layers.splice(targetIdx, 0, item);
    dragIdx = null;
    renderLayers();
}
function dragEnd(e) { e.currentTarget.classList.remove('dragging'); dragIdx = null; }

// ══════════════════════════════════════════
// Coleta de dados para submissão
// ══════════════════════════════════════════

/** Coleta metadados de cada item de áudio (sem o File, que vai via FormData separadamente) */
function collectAudioMeta() {
    const items = [];
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        const activePanel = item.querySelector('.audio-panel.active');
        const type = activePanel ? activePanel.dataset.panelType : 'upload';
        const volRange = activePanel ? activePanel.querySelector('.audio-vol-range') : null;
        const volume = volRange ? parseInt(volRange.value) : 100;

        // Trim values (comuns a upload e omni)
        const trimStart = activePanel.querySelector('.trim-start')?.value.trim();
        const trimEnd = activePanel.querySelector('.trim-end')?.value.trim();

        if (type === 'upload') {
            const fileInput = activePanel.querySelector('.audio-file-input');
            const entry = {
                index: i,
                type: 'upload',
                volume,
                has_file: !!(fileInput && fileInput.files[0]),
            };
            if (trimStart) entry.trim_start = parseFloat(trimStart);
            if (trimEnd) entry.trim_end = parseFloat(trimEnd);
            items.push(entry);
        } else {
            // OmniVoice — checar se já foi pré-gerado
            const omniGenData = item._omniGenerated;

            if (omniGenData && omniGenData.audio_url) {
                // Áudio IA já gerado — enviar como pré-gerado
                const entry = {
                    index: i,
                    type: 'omni_pregenerated',
                    volume,
                    audio_url: omniGenData.audio_url,
                    job_id: omniGenData.job_id,
                };
                if (trimStart) entry.trim_start = parseFloat(trimStart);
                if (trimEnd) entry.trim_end = parseFloat(trimEnd);
                items.push(entry);
            } else {
                // Não gerado ainda — enviar dados crus para gerar no worker
                const text = (activePanel.querySelector('.omni-text-input')?.value || '').trim();
                const activeModeTabs = activePanel.querySelectorAll('.omni-mode-tab.active');
                const mode = activeModeTabs.length ? activeModeTabs[0].dataset.mode : 'clone';
                const voiceId = activePanel.querySelector('.omni-voice-select')?.value || '';
                const presetId = activePanel.querySelector('.omni-preset-select')?.value || '';

                // Voice Design instruct
                let instruct = '';
                if (mode === 'design') {
                    const free = activePanel.querySelector('.omni-d-free')?.value.trim() || '';
                    if (free) {
                        instruct = free;
                    } else {
                        const parts = [
                            activePanel.querySelector('.omni-d-gender')?.value,
                            activePanel.querySelector('.omni-d-age')?.value,
                            activePanel.querySelector('.omni-d-pitch')?.value,
                            activePanel.querySelector('.omni-d-style')?.value,
                        ].filter(Boolean);
                        instruct = parts.join(', ');
                    }
                }

                // Gen params
                const genParams = {};
                ['num_step','guidance_scale','speed','language_id','position_temperature','class_temperature'].forEach(k => {
                    const el = activePanel.querySelector(`.omni-p.${k}`);
                    if (el && el.value.trim() !== '') {
                        genParams[k] = k === 'language_id' ? el.value.trim() : parseFloat(el.value);
                    }
                });
                const denoise = activePanel.querySelector('.omni-p-denoise');
                const pre = activePanel.querySelector('.omni-p-preprocess');
                const post = activePanel.querySelector('.omni-p-postprocess');
                if (denoise) genParams.denoise = denoise.checked;
                if (pre) genParams.preprocess_prompt = pre.checked;
                if (post) genParams.postprocess_output = post.checked;

                const entry = {
                    index: i,
                    type: 'omni',
                    volume,
                    text,
                    mode,
                    voice_id: voiceId,
                    instruct,
                    preset_id: presetId,
                    gen_params: genParams,
                };
                if (trimStart) entry.trim_start = parseFloat(trimStart);
                if (trimEnd) entry.trim_end = parseFloat(trimEnd);
                items.push(entry);
            }
        }
    });
    return items;
}

/** Coleta metadados de cada segmento de imagem de fundo */
function collectBgMeta() {
    const segs = [];
    document.querySelectorAll('#bgSegmentsList .img-segment').forEach((seg, i) => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        const fileInput = seg.querySelector('.bg-img-input');
        segs.push({
            index: i,
            start_sec: startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0,
            end_sec: endInput && endInput.value !== '' ? parseFloat(endInput.value) : null,
            has_file: !!(fileInput && fileInput.files[0]),
        });
    });
    return segs;
}

/** Coleta metadados de cada segmento de imagem sobreposta */
function collectOverlayMeta() {
    const segs = [];
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach((seg, i) => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        const fileInput = seg.querySelector('.overlay-img-input');
        const activePos = seg.querySelector('.overlay-pos-grid button.active');
        const scaleRange = seg.querySelector('.overlay-scale-range');
        // Campos px (controle fino)
        const pxW = seg.querySelector('.overlay-px-w')?.value.trim();
        const pxH = seg.querySelector('.overlay-px-h')?.value.trim();
        const pxX = seg.querySelector('.overlay-px-x')?.value.trim();
        const pxY = seg.querySelector('.overlay-px-y')?.value.trim();

        const entry = {
            index: i,
            start_sec: startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0,
            end_sec: endInput && endInput.value !== '' ? parseFloat(endInput.value) : null,
            position: activePos ? activePos.dataset.pos : 'centro',
            scale: scaleRange ? parseInt(scaleRange.value) : 50,
            has_file: !!(fileInput && fileInput.files[0]),
        };
        // Só envia campos px se preenchidos
        if (pxW) entry.px_width  = parseInt(pxW);
        if (pxH) entry.px_height = parseInt(pxH);
        if (pxX !== '') entry.px_x = parseInt(pxX);
        if (pxY !== '') entry.px_y = parseInt(pxY);

        segs.push(entry);
    });
    return segs;
}

// ══════════════════════════════════════════
// Submit
// ══════════════════════════════════════════
async function submitCompositor() {
    const btn = document.getElementById('btnGenerate');
    const progressSection = document.getElementById('progressSection');
    const resultSection = document.getElementById('resultSection');

    const title = document.getElementById('title').value.trim();
    if (!title) { showToast('Informe o título do vídeo.', 'error'); return; }

    // Validar áudios
    const audioItems = document.querySelectorAll('#audioItemsList .audio-item');
    if (audioItems.length === 0) { showToast('Adicione ao menos um áudio principal.', 'error'); return; }

    let hasAudioError = false;
    audioItems.forEach((item, i) => {
        if (hasAudioError) return;
        const activePanel = item.querySelector('.audio-panel.active');
        const type = activePanel?.dataset.panelType;
        if (type === 'upload') {
            const fileInput = activePanel.querySelector('.audio-file-input');
            if (!fileInput?.files[0]) { showToast(`Áudio ${i+1}: envie um arquivo de áudio.`, 'error'); hasAudioError = true; }
        } else if (type === 'omni') {
            // Se o áudio IA já foi gerado, está ok
            if (item._omniGenerated && item._omniGenerated.audio_url) {
                // OK — áudio já pronto
            } else {
                // Não foi gerado — bloquear e pedir para gerar primeiro
                showToast(`Áudio ${i+1}: gere o áudio IA antes de criar o vídeo. Clique em "🎵 Gerar Áudio IA".`, 'error');
                hasAudioError = true;
            }
        }
    });
    if (hasAudioError) return;

    // Validar imagens de fundo
    const bgSegs = document.querySelectorAll('#bgSegmentsList .img-segment');
    if (bgSegs.length === 0) { showToast('Adicione ao menos uma imagem de fundo.', 'error'); return; }

    let hasBgError = false;
    bgSegs.forEach((seg, i) => {
        if (hasBgError) return;
        const fileInput = seg.querySelector('.bg-img-input');
        if (!fileInput?.files[0]) { showToast(`Fundo ${i+1}: envie uma imagem.`, 'error'); hasBgError = true; }
    });
    if (hasBgError) return;

    btn.disabled = true;
    btn.textContent = '⏳ Enviando...';
    progressSection.classList.remove('hidden');
    resultSection.classList.add('hidden');

    // Montar FormData
    const formData = new FormData();
    formData.set('title', title);
    formData.set('resolution', state.resolution);

    // Metadados JSON
    const audioMeta = collectAudioMeta();
    const bgMeta = collectBgMeta();
    const overlayMeta = collectOverlayMeta();
    formData.set('audio_items_json', JSON.stringify(audioMeta));
    formData.set('bg_segments_json', JSON.stringify(bgMeta));
    formData.set('overlay_segments_json', JSON.stringify(overlayMeta));
    formData.set('animations_json', JSON.stringify(state.selectedAnimations));
    formData.set('elements_json', JSON.stringify(state.selectedElements));
    formData.set('layers_json', JSON.stringify(state.layers));

    // Arquivos de áudio (upload + IA pré-gerada como blob)
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        const activePanel = item.querySelector('.audio-panel.active');
        if (activePanel?.dataset.panelType === 'upload') {
            const fileInput = activePanel.querySelector('.audio-file-input');
            if (fileInput?.files[0]) formData.append(`audio_file_${i}`, fileInput.files[0]);
        } else if (activePanel?.dataset.panelType === 'omni') {
            // Se tem blob do áudio IA pré-gerado, envia como arquivo
            if (item._omniGenerated && item._omniGenerated.blob) {
                formData.append(`audio_file_${i}`, item._omniGenerated.blob, `omni_audio_${i}.wav`);
            }
        }
    });

    // Arquivos de imagem de fundo
    document.querySelectorAll('#bgSegmentsList .img-segment').forEach((seg, i) => {
        const fileInput = seg.querySelector('.bg-img-input');
        if (fileInput?.files[0]) formData.append(`bg_image_${i}`, fileInput.files[0]);
    });

    // Arquivos de imagem sobreposta
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach((seg, i) => {
        const fileInput = seg.querySelector('.overlay-img-input');
        if (fileInput?.files[0]) formData.append(`overlay_image_${i}`, fileInput.files[0]);
    });

    // Áudio secundário
    const secFile = document.getElementById('secondary_audio_file')?.files[0];
    if (secFile) formData.append('secondary_audio_file', secFile);
    formData.set('secondary_audio_volume', document.getElementById('secVolume')?.value || '20');

    try {
        const response = await fetch('/video-compositor/render', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro ao enviar');
        state.jobId = data.job_id;
        showToast(`Job ${data.job_id} criado com sucesso!`, 'success');
        updateProgress('pending', 0, 'Job enviado, aguardando worker...');
        startProgressStream(data.job_id);
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
        progressSection.classList.add('hidden');
    }
}

function startProgressStream(jobId) {
    if (state.eventSource) state.eventSource.close();
    const es = new EventSource(`/api/jobs/${jobId}/stream`);
    state.eventSource = es;
    es.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateProgress(data.status, data.progress, data.detail);
            if (data.status === 'done') { es.close(); showResult(data); }
            else if (data.status === 'error') {
                es.close();
                showToast(`Erro: ${data.detail}`, 'error');
                document.getElementById('btnGenerate').disabled = false;
                document.getElementById('btnGenerate').textContent = '🚀 Gerar Vídeo';
            }
        } catch (e) { /* ignore heartbeat */ }
    };
    es.onerror = () => {
        es.close();
        setTimeout(() => { if (state.jobId) startProgressStream(state.jobId); }, 5000);
    };
}

function updateProgress(status, progress, detail) {
    const statusMap = {
        pending:'⏳ Na fila', preparing:'📦 Preparando', generating_audio:'🎵 Gerando áudio',
        rendering:'🎬 Renderizando', composing:'🎨 Compondo', done:'✅ Concluído', error:'❌ Erro',
    };
    document.getElementById('progressFill').style.width = `${progress}%`;
    document.getElementById('progressLabel').textContent = statusMap[status] || status;
    document.getElementById('progressPercent').textContent = `${Math.round(progress)}%`;
    document.getElementById('progressDetail').textContent = detail || '';
}

function showResult(data) {
    const resultSection = document.getElementById('resultSection');
    resultSection.classList.remove('hidden');
    const link = document.getElementById('resultLink');
    link.href = data.video_url || `/video-compositor/video/${state.jobId}`;
    document.getElementById('btnGenerate').disabled = false;
    document.getElementById('btnGenerate').textContent = '🚀 Gerar Outro Vídeo';
}

// ══════════════════════════════════════════
// Toasts
// ══════════════════════════════════════════
function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// ══════════════════════════════════════════
// Audio Preview: criar player para arquivo selecionado
// ══════════════════════════════════════════
function setupAudioPreviewFromFile(panel, file) {
    const playerWrap = panel.querySelector('.audio-player-wrap');
    const audioEl = panel.querySelector('.audio-preview-el');
    const durationEl = panel.querySelector('.player-duration');
    const trimWrap = panel.querySelector('.audio-trim-wrap');
    if (!playerWrap || !audioEl) return;

    // Revogar URL anterior se existir
    if (audioEl.src && audioEl.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioEl.src);
    }

    const objectUrl = URL.createObjectURL(file);
    audioEl.src = objectUrl;
    playerWrap.classList.add('visible');
    if (trimWrap) { trimWrap.classList.add('visible'); setupTrimListeners(panel); }

    // Mostrar duração quando carregada + recalcular timeline geral
    audioEl.addEventListener('loadedmetadata', () => {
        if (durationEl && isFinite(audioEl.duration)) {
            const dur = audioEl.duration;
            const min = Math.floor(dur / 60);
            const sec = Math.floor(dur % 60);
            durationEl.textContent = `${min}:${sec.toString().padStart(2, '0')}`;
        }
        refreshTimelineUI();
    }, { once: true });
}

function setupAudioPreviewFromUrl(panel, url) {
    const playerWrap = panel.querySelector('.audio-player-wrap');
    const audioEl = panel.querySelector('.audio-preview-el');
    const durationEl = panel.querySelector('.player-duration');
    const trimWrap = panel.querySelector('.audio-trim-wrap');
    if (!playerWrap || !audioEl) return;

    audioEl.src = url;
    playerWrap.classList.add('visible');
    if (trimWrap) { trimWrap.classList.add('visible'); setupTrimListeners(panel); }

    audioEl.addEventListener('loadedmetadata', () => {
        if (durationEl && isFinite(audioEl.duration)) {
            const dur = audioEl.duration;
            const min = Math.floor(dur / 60);
            const sec = Math.floor(dur % 60);
            durationEl.textContent = `${min}:${sec.toString().padStart(2, '0')}`;
        }
        refreshTimelineUI();
    }, { once: true });
}

/** Liga os campos de recorte (trim) do painel ao recálculo da timeline (evita duplicar listener). */
function setupTrimListeners(panel) {
    const trimStart = panel.querySelector('.trim-start');
    const trimEnd = panel.querySelector('.trim-end');
    [trimStart, trimEnd].forEach(el => {
        if (el && !el.dataset.trimBound) {
            el.dataset.trimBound = '1';
            el.addEventListener('input', () => refreshTimelineUI());
        }
    });
}

// ══════════════════════════════════════════
// Gerar Áudio IA na página (OmniVoice inline)
// ══════════════════════════════════════════
async function generateOmniAudio(btn) {
    const audioItem = btn.closest('.audio-item');
    const panel = btn.closest('.audio-panel');
    if (!audioItem || !panel) return;

    // Coletar dados do formulário omni
    const text = (panel.querySelector('.omni-text-input')?.value || '').trim();
    if (!text) { showToast('Informe o texto para a IA gerar o áudio.', 'error'); return; }

    const activeModeTabs = panel.querySelectorAll('.omni-mode-tab.active');
    const mode = activeModeTabs.length ? activeModeTabs[0].dataset.mode : 'clone';
    const voiceId = panel.querySelector('.omni-voice-select')?.value || '';

    if (mode === 'clone' && !voiceId) {
        showToast('Selecione uma voz para clonagem.', 'error');
        return;
    }

    // Voice Design instruct
    let instruct = '';
    if (mode === 'design') {
        const free = panel.querySelector('.omni-d-free')?.value.trim() || '';
        if (free) {
            instruct = free;
        } else {
            const parts = [
                panel.querySelector('.omni-d-gender')?.value,
                panel.querySelector('.omni-d-age')?.value,
                panel.querySelector('.omni-d-pitch')?.value,
                panel.querySelector('.omni-d-style')?.value,
            ].filter(Boolean);
            instruct = parts.join(', ');
        }
        if (!instruct) {
            showToast('Descreva os atributos da voz (Voice Design).', 'error');
            return;
        }
    }

    // Gen params
    const formParams = new FormData();
    formParams.set('text', text);
    formParams.set('mode', mode);
    formParams.set('voice', voiceId);
    formParams.set('instruct', instruct);

    // Parâmetros avançados
    ['num_step','guidance_scale','speed','language_id','position_temperature','class_temperature'].forEach(k => {
        const el = panel.querySelector(`.omni-p.${k}`);
        if (el && el.value.trim() !== '') formParams.set(k, el.value.trim());
    });
    const denoise = panel.querySelector('.omni-p-denoise');
    const pre = panel.querySelector('.omni-p-preprocess');
    const post = panel.querySelector('.omni-p-postprocess');
    if (denoise) formParams.set('denoise', denoise.checked ? '1' : '0');
    if (pre) formParams.set('preprocess_prompt', pre.checked ? '1' : '0');
    if (post) formParams.set('postprocess_output', post.checked ? '1' : '0');

    // UI: estado gerando
    const genSection = panel.querySelector('.omni-gen-section');
    const progressWrap = genSection.querySelector('.omni-progress-wrap');
    const progressFill = genSection.querySelector('.omni-progress-fill');
    const progressLabel = genSection.querySelector('.omni-progress-label');
    const progressPercent = genSection.querySelector('.omni-progress-percent');
    const statusArea = genSection.querySelector('.omni-status-area');

    btn.disabled = true;
    btn.classList.add('generating');
    btn.innerHTML = '⏳ Gerando...';
    progressWrap.classList.add('visible');
    progressFill.style.width = '0%';
    progressLabel.textContent = 'Enviando...';
    progressPercent.textContent = '0%';
    statusArea.innerHTML = '<span class="omni-status-badge pending">⏳ Gerando áudio...</span>';

    // Limpar geração anterior
    audioItem._omniGenerated = null;
    const playerWrap = panel.querySelector('.audio-player-wrap');
    if (playerWrap) playerWrap.classList.remove('visible');
    const trimWrap = panel.querySelector('.audio-trim-wrap');
    if (trimWrap) trimWrap.classList.remove('visible');

    try {
        // POST para gerar
        const response = await fetch('/audio/api/generate', { method: 'POST', body: formParams });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro ao gerar áudio');

        const jobId = data.job_id;
        showToast(`Áudio IA em geração (job ${jobId})...`, 'info');

        // Iniciar SSE para progresso
        if (audioItem._omniEventSource) audioItem._omniEventSource.close();
        const es = new EventSource(`/audio/api/progress/${jobId}/stream`);
        audioItem._omniEventSource = es;

        es.onmessage = async (event) => {
            try {
                const d = JSON.parse(event.data);
                const pct = Math.round(d.progress || 0);
                progressFill.style.width = `${pct}%`;
                progressPercent.textContent = `${pct}%`;
                progressLabel.textContent = d.detail || d.status || 'Processando...';

                if (d.status === 'done') {
                    es.close();
                    audioItem._omniEventSource = null;

                    // Pegar URL do áudio gerado
                    const audioUrl = d.audio_url || `/audio-files/${jobId}.wav`;

                    // Baixar o blob do áudio para enviar junto com o form
                    let blob = null;
                    try {
                        const audioResp = await fetch(audioUrl);
                        if (audioResp.ok) blob = await audioResp.blob();
                    } catch (e) {
                        console.warn('Não foi possível baixar o blob do áudio:', e);
                    }

                    audioItem._omniGenerated = { job_id: jobId, audio_url: audioUrl, blob };

                    // UI: estado pronto
                    btn.disabled = false;
                    btn.classList.remove('generating');
                    btn.classList.add('done');
                    btn.innerHTML = '🔄 Refazer Áudio IA';
                    statusArea.innerHTML = '<span class="omni-status-badge done">✅ Áudio pronto!</span>';
                    progressLabel.textContent = 'Concluído!';

                    // Mostrar player de preview
                    if (blob) {
                        const blobUrl = URL.createObjectURL(blob);
                        setupAudioPreviewFromUrl(panel, blobUrl);
                    } else {
                        setupAudioPreviewFromUrl(panel, audioUrl);
                    }

                    showToast('Áudio IA gerado com sucesso! Escute o preview.', 'success');

                } else if (d.status === 'error') {
                    es.close();
                    audioItem._omniEventSource = null;
                    btn.disabled = false;
                    btn.classList.remove('generating');
                    btn.innerHTML = '🎵 Gerar Áudio IA';
                    statusArea.innerHTML = `<span class="omni-status-badge error">❌ ${d.detail || 'Erro'}</span>`;
                    showToast(`Erro ao gerar áudio: ${d.detail}`, 'error');
                }
            } catch (e) { /* heartbeat */ }
        };

        es.onerror = () => {
            es.close();
            audioItem._omniEventSource = null;
            // Tentar reconectar uma vez
            setTimeout(() => {
                if (!audioItem._omniGenerated) {
                    btn.disabled = false;
                    btn.classList.remove('generating');
                    btn.innerHTML = '🎵 Gerar Áudio IA';
                    statusArea.innerHTML = '<span class="omni-status-badge error">❌ Conexão perdida</span>';
                }
            }, 3000);
        };

    } catch (err) {
        btn.disabled = false;
        btn.classList.remove('generating');
        btn.innerHTML = '🎵 Gerar Áudio IA';
        statusArea.innerHTML = `<span class="omni-status-badge error">❌ ${err.message}</span>`;
        progressWrap.classList.remove('visible');
        showToast(err.message, 'error');
    }
}

// ══════════════════════════════════════════
// Init
// ══════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    // Secondary audio file name display
    const secInput = document.getElementById('secondary_audio_file');
    if (secInput) {
        secInput.addEventListener('change', () => {
            const fn = document.getElementById('secAudioFileName');
            if (fn && secInput.files[0]) { fn.textContent = '✅ ' + secInput.files[0].name; fn.style.display = 'block'; }
        });
    }

    // Timeline: mover o slider atualiza o preview no instante escolhido
    const timeSlider = document.getElementById('previewTimeSlider');
    if (timeSlider) {
        timeSlider.addEventListener('input', () => {
            document.getElementById('previewTimeLabel').textContent = `${(parseFloat(timeSlider.value) || 0).toFixed(1)}s`;
            refreshPreviewNow();
        });
    }

    // Carregar vozes e presets da OmniVoice
    loadOmniVoices();
    loadOmniPresets();

    // Adicionar um áudio e um fundo por padrão
    addAudioItem();
    addBgSegment();

    updateLayers();
    refreshTimelineUI();
});
