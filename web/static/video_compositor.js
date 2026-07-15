/**
 * Vídeo Compositor — Lógica do editor visual v3
 * Suporta: múltiplos áudios, OmniVoice com seleção de voz/preset/configuração,
 *          imagens de fundo por segmento de tempo (cascata automática),
 *          imagens sobrepostas por segmento,
 *          animações/elementos com controles de tempo e intensidade,
 *          animações customizadas (upload de vídeo/GIF).
 */

// ══════════════════════════════════════════
// Estado global
// ══════════════════════════════════════════
const state = {
    selectedAnimations: [],   // [{name:'particulas', start:null, end:null, fullVideo:true, intensity:50}, ...]
    selectedElements: [],     // [{name:'moldura_gold', start:null, end:null, fullVideo:true}, ...]
    layers: [],
    resolution: '1080x1920',
    audioItems: [],
    bgSegments: [],
    overlaySegments: [],
    customAnims: [],          // [{file:File, start, end, position, scale, loop}, ...]
    jobId: null,
    eventSource: null,
    omniVoices: [],
    omniPresets: [],
    totalDuration: 0,
};

let audioItemCounter = 0;
let bgSegmentCounter = 0;
let overlaySegmentCounter = 0;
let customAnimCounter = 0;

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
    wrapper._omniGenerated = null;
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

    const uploadTpl = document.getElementById('tplAudioUpload').content.cloneNode(true);
    panelsWrap.appendChild(uploadTpl);

    const omniTpl = document.getElementById('tplAudioOmni').content.cloneNode(true);
    const omniPanel = omniTpl.querySelector('.audio-panel');
    omniPanel.classList.remove('active');
    panelsWrap.appendChild(omniTpl);

    container.appendChild(wrapper);

    const fileInput = wrapper.querySelector('.audio-file-input');
    const fileName = wrapper.querySelector('.audio-panel[data-panel-type=upload] .file-name');
    const uploadPanel = wrapper.querySelector('.audio-panel[data-panel-type=upload]');
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            fileName.textContent = '✅ ' + fileInput.files[0].name;
            fileName.style.display = 'block';
            setupAudioPreviewFromFile(uploadPanel, fileInput.files[0]);
        }
        updateAudioPreview();
    });

    wrapper.querySelectorAll('.audio-vol-range').forEach(range => {
        range.addEventListener('input', () => {
            range.nextElementSibling.textContent = range.value + '%';
        });
    });

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
    if (item._omniEventSource) {
        item._omniEventSource.close();
        item._omniEventSource = null;
    }
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
// Imagens de Fundo: Adicionar/Remover — Cascata automática
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

    // Configurar cascata automática: start do novo = end do anterior
    const allSegs = container.querySelectorAll('.img-segment');
    const segIndex = Array.from(allSegs).indexOf(added);

    if (segIndex > 0) {
        // Calcular start baseado no end do anterior
        const prevSeg = allSegs[segIndex - 1];
        const prevEnd = prevSeg.querySelector('.seg-end');
        const prevEndVal = prevEnd && prevEnd.value.trim() ? parseFloat(prevEnd.value) : null;
        const startInput = added.querySelector('.seg-start');

        if (prevEndVal !== null) {
            startInput.value = prevEndVal.toFixed(1);
        } else if (state.totalDuration > 0) {
            // Dividir tempo restante igualmente
            const prevStart = parseFloat(prevSeg.querySelector('.seg-start').value || '0');
            const remaining = state.totalDuration - prevStart;
            const half = prevStart + remaining / 2;
            // Setar o end do anterior se estiver vazio
            prevEnd.value = half.toFixed(1);
            startInput.value = half.toFixed(1);
        }

        // Campo start readonly a partir do 2º segmento
        startInput.readOnly = true;
        startInput.classList.add('seg-start-auto');
        // Adicionar hint
        const hintDiv = document.createElement('div');
        hintDiv.className = 'seg-start-auto-hint';
        hintDiv.innerHTML = '🔗 Calculado automaticamente';
        startInput.parentNode.appendChild(hintDiv);
    }

    // Listener no campo end para propagar cascata
    const endInput = added.querySelector('.seg-end');
    if (endInput) {
        endInput.addEventListener('change', () => recalcBgCascadeTimes());
        endInput.addEventListener('blur', () => recalcBgCascadeTimes());
    }

    renumberBgSegments();
    updateLayers();
    refreshTimelineUI();
}

/**
 * Recalcula os tempos de início de todas as imagens de fundo em cascata.
 * O start da imagem N+1 = end da imagem N.
 * O start da primeira imagem é sempre 0.
 */
function recalcBgCascadeTimes() {
    const container = document.getElementById('bgSegmentsList');
    const allSegs = container.querySelectorAll('.img-segment');

    allSegs.forEach((seg, i) => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');

        if (i === 0) {
            // A primeira sempre começa em 0
            startInput.value = '0.0';
            startInput.readOnly = false;
            startInput.classList.remove('seg-start-auto');
            // Remover hint se existir
            const hint = startInput.parentNode.querySelector('.seg-start-auto-hint');
            if (hint) hint.remove();
        } else {
            // Start = end do anterior
            const prevSeg = allSegs[i - 1];
            const prevEnd = prevSeg.querySelector('.seg-end');
            const prevEndVal = prevEnd && prevEnd.value.trim() ? parseFloat(prevEnd.value) : null;

            if (prevEndVal !== null) {
                startInput.value = prevEndVal.toFixed(1);
            }

            // Garantir readonly
            startInput.readOnly = true;
            if (!startInput.classList.contains('seg-start-auto')) {
                startInput.classList.add('seg-start-auto');
                if (!startInput.parentNode.querySelector('.seg-start-auto-hint')) {
                    const hintDiv = document.createElement('div');
                    hintDiv.className = 'seg-start-auto-hint';
                    hintDiv.innerHTML = '🔗 Calculado automaticamente';
                    startInput.parentNode.appendChild(hintDiv);
                }
            }
        }

        checkSegmentTimeWarning(seg);
    });

    refreshPreviewNow();
}

function removeBgSegment(btn) {
    btn.closest('.img-segment').remove();
    renumberBgSegments();
    recalcBgCascadeTimes();
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

function _scaleToPx(seg, scalePercent) {
    const [outW, outH] = state.resolution.split('x').map(Number);
    const imgEl = seg.querySelector('.preview');
    const hasImg = imgEl && imgEl.naturalWidth > 0;

    let w, h;
    if (hasImg) {
        const ratio = imgEl.naturalWidth / imgEl.naturalHeight;
        w = Math.round(outW * scalePercent / 100);
        h = Math.round(w / ratio);
        if (h > outH) {
            h = Math.round(outH * scalePercent / 100);
            w = Math.round(h * ratio);
        }
    } else {
        w = Math.round(outW * scalePercent / 100);
        h = null;
    }
    return { w, h };
}

function _posToPx(posKey, imgW, imgH) {
    const [outW, outH] = state.resolution.split('x').map(Number);
    const w = imgW || 0;
    const h = imgH || 0;
    const pad = Math.round(outW * 0.05);

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
// ══════════════════════════════════════════
function applyFinePositionToEl(overlayEl, pxW, pxH, pxX, pxY) {
    const canvas = document.getElementById('previewCanvas');
    const canvasRect = canvas.getBoundingClientRect();
    const [outW, outH] = state.resolution.split('x').map(Number);
    const scaleX = canvasRect.width / outW;
    const scaleY = canvasRect.height / outH;

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
                preview.onload = () => {
                    _syncFineFromQuick(seg);
                    refreshPreviewNow();
                };
            }
        };
        reader.readAsDataURL(file);
        updateLayers();
    });

    const startInput = seg.querySelector('.seg-start');
    const endInput = seg.querySelector('.seg-end');
    [startInput, endInput].forEach(el => {
        if (!el) return;
        el.addEventListener('input', () => checkSegmentTimeWarning(seg));
        el.addEventListener('change', () => {
            clampSegmentTimes(seg);
            if (type === 'bg') recalcBgCascadeTimes();
            refreshPreviewNow();
        });
        el.addEventListener('blur', () => {
            clampSegmentTimes(seg);
            if (type === 'bg') recalcBgCascadeTimes();
            refreshPreviewNow();
        });
    });
}

// ══════════════════════════════════════════
// Duração total dos áudios (considerando corte/trim)
// ══════════════════════════════════════════

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

function computeTotalDuration() {
    let total = 0;
    document.querySelectorAll('#audioItemsList .audio-item').forEach(item => {
        total += getAudioItemEffectiveDuration(item);
    });
    state.totalDuration = total;
    return total;
}

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

function findActiveSegmentAtTime(segments, t, allowGapFill = true) {
    if (!segments.length) return null;
    const candidates = segments.filter(s => s.start <= t && (s.end === null || t < s.end));
    if (candidates.length) {
        return candidates.reduce((a, b) => (b.start >= a.start ? b : a));
    }
    if (!allowGapFill) return null;

    const before = segments.filter(s => s.start <= t);
    if (before.length) {
        return before.reduce((a, b) => (b.start >= a.start ? b : a));
    }
    return segments.reduce((a, b) => (b.start <= a.start ? b : a));
}

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

function clampSegmentTimes(seg) {
    const total = state.totalDuration;
    const startInput = seg.querySelector('.seg-start');
    const endInput = seg.querySelector('.seg-end');

    if (startInput && !startInput.readOnly) {
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

    document.querySelectorAll('#bgSegmentsList .img-segment').forEach(clampSegmentTimes);
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach(clampSegmentTimes);

    // Recalcular cascata quando a duração total muda
    recalcBgCascadeTimes();

    refreshPreviewNow();
}

function findAllActiveSegmentsAtTime(segments, t) {
    return segments.filter(s => s.start <= t && (s.end === null || t < s.end));
}

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
    const animBadges = state.selectedAnimations.map(a => `<span>${getAnimName(a.name || a)}</span>`).join('');
    const customAnimBadges = document.querySelectorAll('#customAnimsList .custom-anim-item').length;
    const customBadge = customAnimBadges > 0 ? `<span>🎞️ ${customAnimBadges} custom</span>` : '';
    document.getElementById('previewAnimBadges').innerHTML = animBadges + customBadge;
}

function getAnimName(key) {
    const map = {
        particulas:'✨ Partículas', fumaca:'🌫️ Fumaça', brilho:'💎 Brilho',
        fogo:'🔥 Fogo', chuva:'🌧️ Chuva', neve:'❄️ Neve',
        faiscas:'⚡ Faíscas', explosao:'💥 Explosão', luz:'💡 Luz', loop_bg:'🔄 Loop'
    };
    return map[key] || key;
}

function getAnimIcon(key) {
    const map = {
        particulas:'✨', fumaca:'🌫️', brilho:'💎', fogo:'🔥', chuva:'🌧️',
        neve:'❄️', faiscas:'⚡', explosao:'💥', luz:'💡', loop_bg:'🔄'
    };
    return map[key] || '🎬';
}

function getElemName(key) {
    const map = {
        moldura_gold:'🖼️ Moldura', moldura_neon:'💜 Neon', barra_inferior:'▬ Barra',
        caixa_texto:'💬 Caixa', gradiente_top:'🌅 Grad.Sup', gradiente_bottom:'🌆 Grad.Inf',
        sombra_vinheta:'🔲 Vinheta', sombra_radial:'⭕ Radial'
    };
    return map[key] || key;
}

function getElemIcon(key) {
    const map = {
        moldura_gold:'🖼️', moldura_neon:'💜', barra_inferior:'▬', caixa_texto:'💬',
        gradiente_top:'🌅', gradiente_bottom:'🌆', sombra_vinheta:'🔲', sombra_radial:'⭕'
    };
    return map[key] || '✨';
}

// ══════════════════════════════════════════


// ══════════════════════════════════════════
// Animações Customizadas (upload de vídeo/GIF)
// ══════════════════════════════════════════
function addCustomAnim() {
    customAnimCounter++;
    const container = document.getElementById('customAnimsList');
    const tpl = document.getElementById('tplCustomAnim').content.cloneNode(true);
    const item = tpl.querySelector('.custom-anim-item');
    item.dataset.customIdx = customAnimCounter;

    container.appendChild(tpl);

    const added = container.querySelector(`[data-custom-idx="${customAnimCounter}"]`);

    // File input
    const fileInput = added.querySelector('.custom-anim-input');
    const fileName = added.querySelector('.file-name');
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            fileName.textContent = '✅ ' + fileInput.files[0].name;
            fileName.style.display = 'block';
        }
        updateLayers();
    });

    // Scale display
    const scaleRange = added.querySelector('.custom-anim-scale');
    if (scaleRange) {
        scaleRange.addEventListener('input', () => {
            scaleRange.nextElementSibling.textContent = scaleRange.value + '%';
        });
    }

    // Position grid
    added.querySelectorAll('.custom-anim-pos-grid button').forEach(btn => {
        btn.addEventListener('click', () => refreshPreviewNow());
    });

    renumberCustomAnims();
    updateLayers();
}

function removeCustomAnim(btn) {
    btn.closest('.custom-anim-item').remove();
    renumberCustomAnims();
    updateLayers();
    refreshPreviewNow();
}

function selectCustomAnimPos(btn) {
    const grid = btn.closest('.custom-anim-pos-grid');
    grid.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    refreshPreviewNow();
}

function renumberCustomAnims() {
    document.querySelectorAll('#customAnimsList .custom-anim-item').forEach((item, i) => {
        item.querySelector('.custom-anim-num').textContent = i + 1;
        item.querySelector('.custom-anim-title').textContent = `Animação Própria ${i + 1}`;
    });
}

// ══════════════════════════════════════════
// Camadas (drag & drop)
// ══════════════════════════════════════════
function updateLayers() {
    const list = [];
    const bgCount = document.querySelectorAll('#bgSegmentsList .img-segment').length;
    if (bgCount > 0) list.push({ id:'bg', icon:'🖼️', name:`Fundo (${bgCount} imagem${bgCount>1?'s':''})`, type:'background' });
    const ovCount = document.querySelectorAll('#overlaySegmentsList .img-segment').length;
    if (ovCount > 0) list.push({ id:'overlay', icon:'📸', name:`Sobrepostas (${ovCount})`, type:'overlay' });
    const customCount = document.querySelectorAll('#customAnimsList .custom-anim-item').length;
    if (customCount > 0) list.push({ id:'custom_anims', icon:'🎞️', name:`Animações Próprias (${customCount})`, type:'custom_anim' });
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

function collectAudioMeta() {
    const items = [];
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        const activePanel = item.querySelector('.audio-panel.active');
        const type = activePanel ? activePanel.dataset.panelType : 'upload';
        const volRange = activePanel ? activePanel.querySelector('.audio-vol-range') : null;
        const volume = volRange ? parseInt(volRange.value) : 100;

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
            const omniGenData = item._omniGenerated;

            if (omniGenData && omniGenData.audio_url) {
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
                const text = (activePanel.querySelector('.omni-text-input')?.value || '').trim();
                const activeModeTabs = activePanel.querySelectorAll('.omni-mode-tab.active');
                const mode = activeModeTabs.length ? activeModeTabs[0].dataset.mode : 'clone';
                const voiceId = activePanel.querySelector('.omni-voice-select')?.value || '';
                const presetId = activePanel.querySelector('.omni-preset-select')?.value || '';

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

function collectOverlayMeta() {
    const segs = [];
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach((seg, i) => {
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        const fileInput = seg.querySelector('.overlay-img-input');
        const activePos = seg.querySelector('.overlay-pos-grid button.active');
        const scaleRange = seg.querySelector('.overlay-scale-range');
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
        if (pxW) entry.px_width  = parseInt(pxW);
        if (pxH) entry.px_height = parseInt(pxH);
        if (pxX !== '') entry.px_x = parseInt(pxX);
        if (pxY !== '') entry.px_y = parseInt(pxY);

        segs.push(entry);
    });
    return segs;
}

/**
 * Coleta dados expandidos de animações selecionadas (com tempo e intensidade).
 */
function collectAnimationMeta() {
    const result = [];
    document.querySelectorAll('#animationsCtrlList .effect-ctrl-item').forEach(panel => {
        const name = panel.dataset.effectName;
        const fullVideo = panel.querySelector('.effect-full-video')?.checked ?? true;
        const startVal = panel.querySelector('.effect-start')?.value.trim();
        const endVal = panel.querySelector('.effect-end')?.value.trim();
        const intensityEl = panel.querySelector('.effect-intensity');
        const intensity = intensityEl ? parseInt(intensityEl.value) : 50;

        result.push({
            name,
            full_video: fullVideo,
            start_sec: !fullVideo && startVal ? parseFloat(startVal) : null,
            end_sec: !fullVideo && endVal ? parseFloat(endVal) : null,
            intensity,
        });
    });
    return result;
}

/**
 * Coleta dados expandidos de elementos selecionados (com tempo).
 */
function collectElementMeta() {
    const result = [];
    document.querySelectorAll('#elementsCtrlList .effect-ctrl-item').forEach(panel => {
        const name = panel.dataset.effectName;
        const fullVideo = panel.querySelector('.effect-full-video')?.checked ?? true;
        const startVal = panel.querySelector('.effect-start')?.value.trim();
        const endVal = panel.querySelector('.effect-end')?.value.trim();

        result.push({
            name,
            full_video: fullVideo,
            start_sec: !fullVideo && startVal ? parseFloat(startVal) : null,
            end_sec: !fullVideo && endVal ? parseFloat(endVal) : null,
        });
    });
    return result;
}

/**
 * Coleta dados de animações customizadas (upload).
 */
function collectCustomAnimMeta() {
    const result = [];
    document.querySelectorAll('#customAnimsList .custom-anim-item').forEach((item, i) => {
        const fileInput = item.querySelector('.custom-anim-input');
        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        const activePos = item.querySelector('.custom-anim-pos-grid button.active');
        const scaleRange = item.querySelector('.custom-anim-scale');
        const loopCheck = item.querySelector('.custom-anim-loop');

        result.push({
            index: i,
            has_file: !!(fileInput && fileInput.files[0]),
            start_sec: startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0,
            end_sec: endInput && endInput.value !== '' ? parseFloat(endInput.value) : null,
            position: activePos ? activePos.dataset.pos : 'centro',
            scale: scaleRange ? parseInt(scaleRange.value) : 30,
            loop: loopCheck ? loopCheck.checked : true,
        });
    });
    return result;
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
            if (item._omniGenerated && item._omniGenerated.audio_url) {
                // OK
            } else {
                showToast(`Áudio ${i+1}: gere o áudio IA antes de criar o vídeo. Clique em "🎵 Gerar Áudio IA".`, 'error');
                hasAudioError = true;
            }
        }
    });
    if (hasAudioError) return;

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
    progressSection.classList.remove('error'); // Limpa erro anterior
    resultSection.classList.add('hidden');
    state.jobFinished = false; // Reseta flag de fim

    const formData = new FormData();
    formData.set('title', title);
    formData.set('resolution', state.resolution);

    // Metadados JSON
    const audioMeta = collectAudioMeta();
    const bgMeta = collectBgMeta();
    const overlayMeta = collectOverlayMeta();
    const animationMeta = collectAnimationMeta();
    const elementMeta = collectElementMeta();
    const customAnimMeta = collectCustomAnimMeta();

    formData.set('audio_items_json', JSON.stringify(audioMeta));
    formData.set('bg_segments_json', JSON.stringify(bgMeta));
    formData.set('overlay_segments_json', JSON.stringify(overlayMeta));
    formData.set('animations_json', JSON.stringify(animationMeta));
    formData.set('elements_json', JSON.stringify(elementMeta));
    formData.set('custom_anims_json', JSON.stringify(customAnimMeta));
    formData.set('layers_json', JSON.stringify(state.layers));

    // Arquivos de áudio
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        const activePanel = item.querySelector('.audio-panel.active');
        if (activePanel?.dataset.panelType === 'upload') {
            const fileInput = activePanel.querySelector('.audio-file-input');
            if (fileInput?.files[0]) formData.append(`audio_file_${i}`, fileInput.files[0]);
        } else if (activePanel?.dataset.panelType === 'omni') {
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

    // Arquivos de animação customizada
    document.querySelectorAll('#customAnimsList .custom-anim-item').forEach((item, i) => {
        const fileInput = item.querySelector('.custom-anim-input');
        if (fileInput?.files[0]) formData.append(`custom_anim_${i}`, fileInput.files[0]);
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
            if (data.status === 'done') { 
                state.jobFinished = true;
                es.close(); 
                showResult(data); 
            }
            else if (data.status === 'error') {
                state.jobFinished = true;
                es.close();
                showToast(`Erro: ${data.detail}`, 'error');
                document.getElementById('btnGenerate').disabled = false;
                document.getElementById('btnGenerate').textContent = '🚀 Gerar Vídeo';
            }
        } catch (e) { /* ignore heartbeat */ }
    };
    es.onerror = () => {
        es.close();
        if (!state.jobFinished) {
            setTimeout(() => { if (state.jobId && !state.jobFinished) startProgressStream(state.jobId); }, 5000);
        }
    };
}

function updateProgress(status, progress, detail) {
    const statusMap = {
        pending:'⏳ Na fila', preparing:'📦 Preparando', generating_audio:'🎵 Gerando áudio',
        rendering:'🎬 Renderizando', composing:'🎨 Compondo', done:'✅ Concluído', error:'❌ Erro',
    };
    
    const progressSection = document.getElementById('progressSection');
    if (status === 'error') {
        progressSection.classList.add('error');
    } else {
        progressSection.classList.remove('error');
    }

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

    if (audioEl.src && audioEl.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioEl.src);
    }

    const objectUrl = URL.createObjectURL(file);
    audioEl.src = objectUrl;
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

    const text = (panel.querySelector('.omni-text-input')?.value || '').trim();
    if (!text) { showToast('Informe o texto para a IA gerar o áudio.', 'error'); return; }

    const activeModeTabs = panel.querySelectorAll('.omni-mode-tab.active');
    const mode = activeModeTabs.length ? activeModeTabs[0].dataset.mode : 'clone';
    const voiceId = panel.querySelector('.omni-voice-select')?.value || '';

    if (mode === 'clone' && !voiceId) {
        showToast('Selecione uma voz para clonagem.', 'error');
        return;
    }

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

    const formParams = new FormData();
    formParams.set('text', text);
    formParams.set('mode', mode);
    formParams.set('voice', voiceId);
    formParams.set('instruct', instruct);

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

    audioItem._omniGenerated = null;
    const playerWrap = panel.querySelector('.audio-player-wrap');
    if (playerWrap) playerWrap.classList.remove('visible');
    const trimWrap = panel.querySelector('.audio-trim-wrap');
    if (trimWrap) trimWrap.classList.remove('visible');

    try {
        const response = await fetch('/audio/api/generate', { method: 'POST', body: formParams });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro ao gerar áudio');

        const jobId = data.job_id;
        showToast(`Áudio IA em geração (job ${jobId})...`, 'info');

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

                    const audioUrl = d.audio_url || `/audio-files/${jobId}.wav`;

                    let blob = null;
                    try {
                        const audioResp = await fetch(audioUrl);
                        if (audioResp.ok) blob = await audioResp.blob();
                    } catch (e) {
                        console.warn('Não foi possível baixar o blob do áudio:', e);
                    }

                    audioItem._omniGenerated = { job_id: jobId, audio_url: audioUrl, blob };

                    btn.disabled = false;
                    btn.classList.remove('generating');
                    btn.classList.add('done');
                    btn.innerHTML = '🔄 Refazer Áudio IA';
                    statusArea.innerHTML = '<span class="omni-status-badge done">✅ Áudio pronto!</span>';
                    progressLabel.textContent = 'Concluído!';

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
    const secInput = document.getElementById('secondary_audio_file');
    if (secInput) {
        secInput.addEventListener('change', () => {
            const fn = document.getElementById('secAudioFileName');
            if (fn && secInput.files[0]) { fn.textContent = '✅ ' + secInput.files[0].name; fn.style.display = 'block'; }
        });
    }

    const timeSlider = document.getElementById('previewTimeSlider');
    if (timeSlider) {
        timeSlider.addEventListener('input', () => {
            document.getElementById('previewTimeLabel').textContent = `${(parseFloat(timeSlider.value) || 0).toFixed(1)}s`;
            refreshPreviewNow();
        });
    }

    loadOmniVoices();
    loadOmniPresets();

    addAudioItem();
    addBgSegment();

    updateLayers();
    refreshTimelineUI();
});
