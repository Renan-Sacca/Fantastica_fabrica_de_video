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
    // Scene mode
    scenes: [],
    useEventTimeline: false,
    sceneResourceDurations: {},
    resolvedTimeline: null,
    totalDurationScenes: 0,
};

let audioItemCounter = 0;
let bgSegmentCounter = 0;
let overlaySegmentCounter = 0;
let customAnimCounter = 0;
let textOverlayCounter = 0;
let secAudioCounter = 0;

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
    if (state.useEventTimeline) {
        if (!state.resolvedTimeline) return [];
        return Array.from(document.querySelectorAll('#scenesList .scene-element')).filter(el => {
            const sceneId = el.closest('.scene-card').dataset.sceneId;
            const scene = state.scenes.find(s => s.scene_id === sceneId);
            const elConfig = scene?.elements.find(e => e.id === el.dataset.elementId);
            return elConfig && elConfig.type === 'background';
        }).map(seg => {
            const id = seg.dataset.elementId;
            const times = state.resolvedTimeline.resolved.get(id);
            const start = times ? times.start : 0;
            const end = times ? times.end : null;
            return { seg, start, end };
        });
    }

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
    if (state.useEventTimeline) {
        if (!state.resolvedTimeline) return [];
        return Array.from(document.querySelectorAll('#scenesList .scene-element')).filter(el => {
            const sceneId = el.closest('.scene-card').dataset.sceneId;
            const scene = state.scenes.find(s => s.scene_id === sceneId);
            const elConfig = scene?.elements.find(e => e.id === el.dataset.elementId);
            return elConfig && (elConfig.type === 'overlay' || elConfig.type === 'custom_anim');
        }).map(seg => {
            const id = seg.dataset.elementId;
            const times = state.resolvedTimeline.resolved.get(id);
            const start = times ? times.start : 0;
            const end = times ? times.end : null;
            return { seg, start, end };
        });
    }

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
    const activeTextList = findAllActiveSegmentsAtTime(getTextOverlaysData(), t);

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

    updatePreview(bgUrl, activeOverlays, activeTextList, t);
    updateTimelineStatusLabel(activeBg, activeOvList);
}

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

const FONT_FAMILY_MAP = {
    'sans': {
        regular: '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        bold: '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        italic: '/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf',
        bold_italic: '/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf',
        name: 'Arial, "Liberation Sans", sans-serif'
    },
    'serif': {
        regular: '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
        bold: '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
        italic: '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf',
        bold_italic: '/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf',
        name: '"Times New Roman", "Liberation Serif", serif'
    },
    'mono': {
        regular: '/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf',
        bold: '/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf',
        italic: '/usr/share/fonts/truetype/liberation/LiberationMono-Italic.ttf',
        bold_italic: '/usr/share/fonts/truetype/liberation/LiberationMono-BoldItalic.ttf',
        name: '"Courier New", "Liberation Mono", monospace'
    },
    'free_sans': {
        regular: '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
        bold: '/usr/share/fonts/truetype/freefont/FreeSansBold.ttf',
        italic: '/usr/share/fonts/truetype/freefont/FreeSansOblique.ttf',
        bold_italic: '/usr/share/fonts/truetype/freefont/FreeSansBoldOblique.ttf',
        name: 'Arial, FreeSans, sans-serif'
    },
    'free_serif': {
        regular: '/usr/share/fonts/truetype/freefont/FreeSerif.ttf',
        bold: '/usr/share/fonts/truetype/freefont/FreeSerifBold.ttf',
        italic: '/usr/share/fonts/truetype/freefont/FreeSerifItalic.ttf',
        bold_italic: '/usr/share/fonts/truetype/freefont/FreeSerifBoldItalic.ttf',
        name: '"Times New Roman", FreeSerif, serif'
    },
    'free_mono': {
        regular: '/usr/share/fonts/truetype/freefont/FreeMono.ttf',
        bold: '/usr/share/fonts/truetype/freefont/FreeMonoBold.ttf',
        italic: '/usr/share/fonts/truetype/freefont/FreeMonoOblique.ttf',
        bold_italic: '/usr/share/fonts/truetype/freefont/FreeMonoBoldOblique.ttf',
        name: '"Courier New", FreeMono, monospace'
    }
};

function getResolvedFont(familyKey, isBold, isItalic) {
    const family = FONT_FAMILY_MAP[familyKey] || FONT_FAMILY_MAP['sans'];
    if (isBold && isItalic) return { file: family.bold_italic, style: 'italic', weight: 'bold', family: family.name };
    if (isBold) return { file: family.bold, style: 'normal', weight: 'bold', family: family.name };
    if (isItalic) return { file: family.italic, style: 'italic', weight: 'normal', family: family.name };
    return { file: family.regular, style: 'normal', weight: 'normal', family: family.name };
}

function getTextOverlaysData() {
    if (state.useEventTimeline) {
        if (!state.resolvedTimeline) return [];
        const list = [];
        document.querySelectorAll('#scenesList .scene-element').forEach(item => {
            const sceneId = item.closest('.scene-card').dataset.sceneId;
            const scene = state.scenes.find(s => s.scene_id === sceneId);
            const elConfig = scene?.elements.find(e => e.id === item.dataset.elementId);
            if (!elConfig || elConfig.type !== 'text') return;

            const id = elConfig.id;
            const times = state.resolvedTimeline.resolved.get(id);
            const start = times ? times.start : 0;
            const end = times ? times.end : null;

            const props = elConfig.properties || {};
            const fontResolved = getResolvedFont(props.font || 'sans', props.bold || false, props.italic || false);

            list.push({
                text: props.text || '',
                font: fontResolved.file,
                fontFamily: fontResolved.family,
                fontStyle: fontResolved.style,
                fontWeight: fontResolved.weight,
                size: props.size || 48,
                color: props.color || '#ffffff',
                start,
                end,
                position: props.position || 'centro',
                px_x: null,
                px_y: null,
                seg: item
            });
        });
        return list;
    }

    const list = [];
    document.querySelectorAll('#textOverlaysList .text-overlay-item').forEach(item => {
        const text = item.querySelector('.text-content')?.value || '';
        const fontKey = item.querySelector('.text-font')?.value || 'sans';
        const isBold = item.querySelector('.text-bold')?.checked || false;
        const isItalic = item.querySelector('.text-italic')?.checked || false;
        const size = parseInt(item.querySelector('.text-size')?.value || '48');
        const color = item.querySelector('.text-color')?.value || '#ffffff';
        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        const activePos = item.querySelector('.text-pos-grid button.active');

        const pxX = item.querySelector('.text-px-x')?.value.trim();
        const pxY = item.querySelector('.text-px-y')?.value.trim();

        const start = startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0;
        const end = endInput && endInput.value !== '' ? parseFloat(endInput.value) : null;
        const position = activePos ? activePos.dataset.pos : 'centro';

        const fontResolved = getResolvedFont(fontKey, isBold, isItalic);

        list.push({
            text,
            font: fontResolved.file,
            fontFamily: fontResolved.family,
            fontStyle: fontResolved.style,
            fontWeight: fontResolved.weight,
            size,
            color,
            start,
            end,
            position,
            px_x: pxX !== '' && pxX !== undefined ? parseFloat(pxX) : null,
            px_y: pxY !== '' && pxY !== undefined ? parseFloat(pxY) : null,
            seg: item
        });
    });
    return list;
}

function updatePreview(bgUrl, activeOverlays, activeTexts, t) {
    const bgEl = document.getElementById('previewBg');
    const overlaysContainer = document.getElementById('previewOverlaysContainer');
    const textsContainer = document.getElementById('previewTextsContainer');
    const placeholder = document.getElementById('previewPlaceholder');
    const previewCanvas = document.getElementById('previewCanvas');

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

    if (textsContainer && previewCanvas) {
        textsContainer.innerHTML = '';
        const canvasW = previewCanvas.clientWidth || 360;
        const [w, h] = state.resolution.split('x').map(Number);
        const scaleFactor = canvasW / w;

        (activeTexts || []).forEach(txt => {
            const div = document.createElement('div');
            div.className = 'preview-text';
            div.textContent = txt.text;

            const scaledSize = Math.max(8, txt.size * scaleFactor);
            div.style.fontSize = `${scaledSize}px`;
            div.style.color = txt.color;

            div.style.fontFamily = txt.fontFamily || 'Arial, "Liberation Sans", sans-serif';
            div.style.fontStyle = txt.fontStyle || 'normal';
            div.style.fontWeight = txt.fontWeight || 'bold';

            if (txt.px_x !== null || txt.px_y !== null) {
                applyFinePositionToEl(div, null, null, txt.px_x, txt.px_y);
            } else {
                const p = OVERLAY_POS_MAP[txt.position] || OVERLAY_POS_MAP['centro'];
                div.style.top = p.top;
                div.style.left = p.left;
                div.style.right = p.right;
                div.style.bottom = p.bottom;
                div.style.transform = p.transform;
            }

            textsContainer.appendChild(div);
        });
    }

    // Animações badges
    let animBadges = '';
    let customAnimBadgesCount = 0;

    if (state.useEventTimeline) {
        if (state.resolvedTimeline) {
            const activeAnims = [];
            state.scenes.forEach(scene => {
                scene.elements.forEach(el => {
                    const times = state.resolvedTimeline.resolved.get(el.id);
                    if (times && times.start <= t && (times.end === null || t < times.end)) {
                        if (el.type === 'animation') {
                            activeAnims.push(el.properties?.name || el.label);
                        } else if (el.type === 'custom_anim') {
                            customAnimBadgesCount++;
                        }
                    }
                });
            });
            animBadges = activeAnims.map(name => `<span>${getAnimName(name)}</span>`).join('');
        }
    } else {
        animBadges = state.selectedAnimations.map(a => `<span>${getAnimName(a.name || a)}</span>`).join('');
        customAnimBadgesCount = document.querySelectorAll('#customAnimsList .custom-anim-item').length;
    }

    const customBadge = customAnimBadgesCount > 0 ? `<span>🎞️ ${customAnimBadgesCount} custom</span>` : '';
    document.getElementById('previewAnimBadges').innerHTML = animBadges + customBadge;
}

window.addEventListener('resize', () => refreshPreviewNow());

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
// Textos sobrepostos
// ══════════════════════════════════════════
function addTextOverlay() {
    textOverlayCounter++;
    const container = document.getElementById('textOverlaysList');
    const tpl = document.getElementById('tplTextOverlay').content.cloneNode(true);
    const item = tpl.querySelector('.text-overlay-item');
    item.dataset.textIdx = textOverlayCounter;
    container.appendChild(tpl);

    const added = container.querySelector(`[data-text-idx="${textOverlayCounter}"]`);

    // Color picker label update
    const colorInput = added.querySelector('.text-color');
    const colorLabel = added.querySelector('.text-color-label');
    if (colorInput && colorLabel) {
        colorInput.addEventListener('input', () => {
            colorLabel.textContent = colorInput.value.toUpperCase();
            colorLabel.style.color = colorInput.value;
            refreshPreviewNow();
        });
    }

    // Live preview update event listeners
    added.querySelector('.text-content')?.addEventListener('input', () => refreshPreviewNow());
    added.querySelector('.text-font')?.addEventListener('change', () => refreshPreviewNow());
    added.querySelector('.text-bold')?.addEventListener('change', () => refreshPreviewNow());
    added.querySelector('.text-italic')?.addEventListener('change', () => refreshPreviewNow());
    added.querySelector('.text-size')?.addEventListener('input', () => refreshPreviewNow());
    added.querySelector('.seg-start')?.addEventListener('input', () => refreshPreviewNow());
    added.querySelector('.seg-end')?.addEventListener('input', () => refreshPreviewNow());
    added.querySelector('.text-px-x')?.addEventListener('input', () => refreshPreviewNow());
    added.querySelector('.text-px-y')?.addEventListener('input', () => refreshPreviewNow());

    renumberTextOverlays();
    updateLayers();
    refreshPreviewNow();
}

function removeTextOverlay(btn) {
    btn.closest('.text-overlay-item').remove();
    renumberTextOverlays();
    updateLayers();
    refreshPreviewNow();
}

function _syncTextFineFromQuick(item) {
    const text = item.querySelector('.text-content')?.value || '';
    const size = parseInt(item.querySelector('.text-size')?.value || '48');
    const activePos = item.querySelector('.text-pos-grid button.active');
    if (!activePos) return;

    const posKey = activePos.dataset.pos || 'centro';
    
    // Aproximação da caixa de texto para o cálculo de posicionamento fino
    const charCount = text.length || 10;
    const w = Math.round(charCount * size * 0.55);
    const h = Math.round(size * 1.25);

    const { x, y } = _posToPx(posKey, w, h);

    const pxX = item.querySelector('.text-px-x');
    const pxY = item.querySelector('.text-px-y');

    if (pxX) pxX.value = x;
    if (pxY) pxY.value = y;
}

function selectTextPos(btn) {
    const grid = btn.closest('.text-pos-grid');
    grid.querySelectorAll('button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const item = btn.closest('.text-overlay-item');
    if (item) _syncTextFineFromQuick(item);
    refreshPreviewNow();
}

function renumberTextOverlays() {
    document.querySelectorAll('#textOverlaysList .text-overlay-item').forEach((item, i) => {
        item.querySelector('.text-overlay-num').textContent = i + 1;
        item.querySelector('.text-overlay-title').textContent = `Texto ${i + 1}`;
    });
}

// ══════════════════════════════════════════
// Áudios secundários (múltiplos)
// ══════════════════════════════════════════
function addSecAudio() {
    secAudioCounter++;
    const container = document.getElementById('secAudioList');
    const tpl = document.getElementById('tplSecAudio').content.cloneNode(true);
    const item = tpl.querySelector('.sec-audio-item');
    item.dataset.secIdx = secAudioCounter;
    container.appendChild(tpl);

    const added = container.querySelector(`[data-sec-idx="${secAudioCounter}"]`);

    // File input
    const fileInput = added.querySelector('.sec-audio-input');
    const fileName = added.querySelector('.file-name');
    fileInput.addEventListener('change', () => {
        if (fileInput.files[0]) {
            fileName.textContent = '✅ ' + fileInput.files[0].name;
            fileName.style.display = 'block';
        }
    });

    // Volume display
    const volRange = added.querySelector('.sec-audio-vol');
    const volDisplay = added.querySelector('.sec-audio-vol-display');
    if (volRange && volDisplay) {
        volRange.addEventListener('input', () => {
            volDisplay.textContent = volRange.value + '%';
        });
    }

    renumberSecAudios();
}

function removeSecAudio(btn) {
    btn.closest('.sec-audio-item').remove();
    renumberSecAudios();
}

function renumberSecAudios() {
    document.querySelectorAll('#secAudioList .sec-audio-item').forEach((item, i) => {
        item.querySelector('.sec-audio-num').textContent = i + 1;
        item.querySelector('.sec-audio-title').textContent = `Áudio Secundário ${i + 1}`;
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
    const txtCount = document.querySelectorAll('#textOverlaysList .text-overlay-item').length;
    if (txtCount > 0) list.push({ id:'text_overlays', icon:'📝', name:`Textos (${txtCount})`, type:'text_overlay' });
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

/**
 * Coleta dados de textos sobrepostos.
 */
function collectTextOverlayMeta() {
    const result = [];
    getTextOverlaysData().forEach((txt, i) => {
        result.push({
            index: i,
            text: txt.text,
            font: txt.font,
            size: txt.size,
            color: txt.color,
            start_sec: txt.start,
            end_sec: txt.end,
            position: txt.position,
            px_x: txt.px_x,
            px_y: txt.px_y
        });
    });
    return result;
}

/**
 * Coleta dados dos áudios secundários.
 */
function collectSecAudioMeta() {
    const result = [];
    document.querySelectorAll('#secAudioList .sec-audio-item').forEach((item, i) => {
        const fileInput = item.querySelector('.sec-audio-input');
        const volRange = item.querySelector('.sec-audio-vol');
        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        const loopCheck = item.querySelector('.sec-audio-loop');

        result.push({
            index: i,
            has_file: !!(fileInput && fileInput.files[0]),
            volume: volRange ? parseInt(volRange.value) : 20,
            start_sec: startInput && startInput.value !== '' ? parseFloat(startInput.value) : 0,
            end_sec: endInput && endInput.value !== '' ? parseFloat(endInput.value) : null,
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

    // ── Modo Cenas: montar submit a partir das cenas resolvidas ──
    if (state.useEventTimeline && state.scenes && state.scenes.length > 0) {
        await submitCompositorSceneMode(btn, title);
        return;
    }

    // ── Modo Clássico (abaixo) ──
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
    const textOverlayMeta = collectTextOverlayMeta();
    const secAudioMeta = collectSecAudioMeta();

    formData.set('audio_items_json', JSON.stringify(audioMeta));
    formData.set('bg_segments_json', JSON.stringify(bgMeta));
    formData.set('overlay_segments_json', JSON.stringify(overlayMeta));
    formData.set('animations_json', JSON.stringify(animationMeta));
    formData.set('elements_json', JSON.stringify(elementMeta));
    formData.set('custom_anims_json', JSON.stringify(customAnimMeta));
    formData.set('text_overlays_json', JSON.stringify(textOverlayMeta));
    formData.set('sec_audios_json', JSON.stringify(secAudioMeta));
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

    // Arquivos de áudio secundário
    document.querySelectorAll('#secAudioList .sec-audio-item').forEach((item, i) => {
        const fileInput = item.querySelector('.sec-audio-input');
        if (fileInput?.files[0]) formData.append(`sec_audio_file_${i}`, fileInput.files[0]);
    });

    try {
        const response = await fetch('/video-compositor/render', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro ao enviar');
        
        showToast(`Vídeo "${title}" enviado com sucesso!`, 'success');
        
        // Adicionar à fila visual
        addToQueue(data.job_id, title);
        
        // Resetar título e habilitar o botão para gerar outros
        document.getElementById('title').value = '';
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
    }
}

function addToQueue(jobId, title) {
    const queueContainer = document.getElementById('compositor-queue');
    if (!queueContainer) return;

    const item = document.createElement('div');
    item.className = 'vb-queue-item';
    item.id = `qi-${jobId}`;
    item.innerHTML = `
        <div class="qi-header">
            <span class="qi-title">🎬 ${escapeHtml(title)}</span>
            <span class="qi-status pending">⏳ Na fila</span>
        </div>
        <div class="vb-progress">
            <div class="bar"><div class="fill" style="width: 5%;"></div></div>
        </div>
        <div class="qi-detail">Aguardando worker...</div>
    `;
    queueContainer.prepend(item);

    trackJobProgress(jobId);
}

function trackJobProgress(jobId) {
    const item = document.getElementById(`qi-${jobId}`);
    if (!item) return;

    const statusEl = item.querySelector('.qi-status');
    const fillEl = item.querySelector('.fill');
    const detailEl = item.querySelector('.qi-detail');

    const es = new EventSource(`/api/jobs/${jobId}/stream`);

    es.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data);
            if (msg.progress !== undefined) {
                fillEl.style.width = msg.progress + '%';
            }
            if (msg.detail) {
                detailEl.textContent = msg.detail;
            }
            
            const statusMap = {
                pending: { label: '⏳ Na fila', class: 'pending' },
                preparing: { label: '📦 Preparando', class: 'processing' },
                generating_audio: { label: '🎵 Áudio', class: 'processing' },
                rendering: { label: '🎬 Renderizando', class: 'processing' },
                composing: { label: '🎨 Compondo', class: 'processing' },
                done: { label: '✅ Pronto', class: 'done' },
                error: { label: '❌ Erro', class: 'error' }
            };

            const info = statusMap[msg.status];
            if (info) {
                statusEl.textContent = info.label;
                statusEl.className = `qi-status ${info.class}`;
            }

            if (msg.status === 'done') {
                es.close();
                fillEl.style.width = '100%';
                detailEl.innerHTML = `<a href="/video-compositor/video/${jobId}" class="qi-link">Ver detalhes →</a>`;
            }
            if (msg.status === 'error') {
                es.close();
                fillEl.style.width = '0%';
                detailEl.textContent = msg.detail || 'Erro desconhecido';
            }
        } catch (e) {}
    };

    es.onerror = () => {
        es.close();
        detailEl.textContent = 'Conexão perdida. Verifique no histórico.';
    };
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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

            // Suporte Modo Cenas
            if (state.useEventTimeline) {
                const sceneEl = panel.closest('.scene-element');
                if (sceneEl && sceneEl.dataset.elementId) {
                    if (!state.sceneResourceDurations) state.sceneResourceDurations = {};
                    state.sceneResourceDurations[sceneEl.dataset.elementId] = dur;
                    resolveAndRefreshTimeline();
                }
            }
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

            // Suporte Modo Cenas
            if (state.useEventTimeline) {
                const sceneEl = panel.closest('.scene-element');
                if (sceneEl && sceneEl.dataset.elementId) {
                    if (!state.sceneResourceDurations) state.sceneResourceDurations = {};
                    state.sceneResourceDurations[sceneEl.dataset.elementId] = dur;
                    resolveAndRefreshTimeline();
                }
            }
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
// Templates: Salvar / Carregar / Aplicar
// ══════════════════════════════════════════

/**
 * Coleta todo o estado atual do editor num JSON limpo (sem arquivos).
 */
function collectTemplateData() {
    const overlayMeta = collectOverlayMeta().map(o => {
        const { has_file, ...rest } = o;
        return rest;
    });

    const bgMeta = collectBgMeta().map(b => {
        const { has_file, ...rest } = b;
        return rest;
    });

    const customAnimMeta = collectCustomAnimMeta().map(c => {
        const { has_file, ...rest } = c;
        return rest;
    });

    const secAudioMeta = collectSecAudioMeta().map(s => {
        const { has_file, ...rest } = s;
        return rest;
    });

    // Quantidade de áudios e seus tipos (upload/omni), sem conteúdo
    const audioSlots = [];
    document.querySelectorAll('#audioItemsList .audio-item').forEach((item, i) => {
        const activePanel = item.querySelector('.audio-panel.active');
        const type = activePanel ? activePanel.dataset.panelType : 'upload';
        const volRange = activePanel ? activePanel.querySelector('.audio-vol-range') : null;
        audioSlots.push({
            index: i,
            type: type,
            volume: volRange ? parseInt(volRange.value) : 100,
        });
    });

    return {
        resolution: state.resolution,
        audio_slots: audioSlots,
        bg_segments: bgMeta,
        overlay_segments: overlayMeta,
        animations: collectAnimationMeta(),
        elements: collectElementMeta(),
        custom_anims: customAnimMeta,
        text_overlays: collectTextOverlayMeta(),
        sec_audios: secAudioMeta,
        layers: state.layers,
    };
}

/**
 * Abre o modal de salvar template.
 */
function openSaveTemplateModal() {
    const modal = document.getElementById('templateSaveModal');
    if (!modal) return;
    modal.classList.add('open');
    document.getElementById('tplSaveName').value = '';
    document.getElementById('tplSaveDesc').value = '';
    document.getElementById('tplSaveName').focus();
}

function closeSaveTemplateModal() {
    document.getElementById('templateSaveModal')?.classList.remove('open');
}

async function confirmSaveTemplate() {
    const name = document.getElementById('tplSaveName').value.trim();
    if (!name) { showToast('Informe o nome do template.', 'error'); return; }
    const description = document.getElementById('tplSaveDesc').value.trim();
    const templateData = collectTemplateDataWithScenes();

    const btn = document.getElementById('tplSaveBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Salvando...';

    try {
        const resp = await fetch('/video-compositor/api/templates', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, template_data: templateData }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Erro ao salvar');
        showToast(`Template "${name}" salvo com sucesso!`, 'success');
        closeSaveTemplateModal();
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '💾 Salvar';
    }
}

/**
 * Abre o modal de carregar template.
 */
async function openLoadTemplateModal() {
    const modal = document.getElementById('templateLoadModal');
    if (!modal) return;
    modal.classList.add('open');

    const listEl = document.getElementById('tplLoadList');
    listEl.innerHTML = '<div style="text-align:center; padding:30px; opacity:.5;">⏳ Carregando...</div>';

    try {
        const resp = await fetch('/video-compositor/api/templates');
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Erro ao carregar');

        const tpls = data.templates || [];
        if (tpls.length === 0) {
            listEl.innerHTML = '<div style="text-align:center; padding:30px; opacity:.5;"><span style="font-size:2rem; display:block; margin-bottom:8px;">📂</span>Nenhum template salvo ainda</div>';
            return;
        }

        listEl.innerHTML = tpls.map(t => {
            const date = t.created_at ? new Date(t.created_at).toLocaleDateString('pt-BR', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' }) : '';
            const desc = t.description ? `<div class="tpl-item-desc">${escapeHtml(t.description)}</div>` : '';
            const resLabel = t.template_data?.resolution || '—';
            const overlayCount = (t.template_data?.overlay_segments || []).length;
            const textCount = (t.template_data?.text_overlays || []).length;
            const animCount = (t.template_data?.animations || []).length;

            const badges = [];
            if (resLabel !== '—') badges.push(`📐 ${resLabel}`);
            if (overlayCount) badges.push(`📸 ${overlayCount} overlay${overlayCount > 1 ? 's' : ''}`);
            if (textCount) badges.push(`📝 ${textCount} texto${textCount > 1 ? 's' : ''}`);
            if (animCount) badges.push(`✨ ${animCount} anim.`);

            return `
            <div class="tpl-item" data-tpl-id="${t.template_id}">
                <div class="tpl-item-header">
                    <div class="tpl-item-info">
                        <div class="tpl-item-name">${escapeHtml(t.name)}</div>
                        ${desc}
                        <div class="tpl-item-badges">${badges.map(b => `<span>${b}</span>`).join('')}</div>
                        <div class="tpl-item-date">${date}</div>
                    </div>
                    <div class="tpl-item-actions">
                        <button type="button" class="vc-btn vc-btn-primary vc-btn-sm" onclick="loadTemplate('${t.template_id}')">📂 Carregar</button>
                        <button type="button" class="vc-btn vc-btn-danger vc-btn-sm" onclick="deleteTemplate('${t.template_id}', this)">🗑️</button>
                    </div>
                </div>
            </div>`;
        }).join('');

    } catch (e) {
        listEl.innerHTML = `<div style="text-align:center; padding:30px; color:#ef4444;">❌ ${e.message}</div>`;
    }
}

function closeLoadTemplateModal() {
    document.getElementById('templateLoadModal')?.classList.remove('open');
}

/**
 * Carrega um template específico e aplica no editor.
 */
async function loadTemplate(templateId) {
    try {
        const resp = await fetch(`/video-compositor/api/templates/${templateId}`);
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Erro ao carregar template');

        const td = data.template?.template_data;
        if (!td) throw new Error('Template sem dados');

        applyTemplateDataWithScenes(td);
        closeLoadTemplateModal();
        showToast(`Template "${data.template.name}" carregado!`, 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

/**
 * Deleta um template.
 */
async function deleteTemplate(templateId, btn) {
    if (!confirm('Tem certeza que deseja excluir este template?')) return;

    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '⏳';

    try {
        const resp = await fetch(`/video-compositor/api/templates/${templateId}`, { method: 'DELETE' });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || 'Erro ao deletar');

        const item = btn.closest('.tpl-item');
        if (item) {
            item.style.opacity = '0';
            item.style.transform = 'translateX(20px)';
            item.style.transition = 'all .3s';
            setTimeout(() => item.remove(), 300);
        }
        showToast('Template excluído!', 'success');

        // Se lista ficou vazia
        setTimeout(() => {
            const listEl = document.getElementById('tplLoadList');
            if (listEl && !listEl.querySelector('.tpl-item')) {
                listEl.innerHTML = '<div style="text-align:center; padding:30px; opacity:.5;"><span style="font-size:2rem; display:block; margin-bottom:8px;">📂</span>Nenhum template salvo</div>';
            }
        }, 350);
    } catch (e) {
        showToast(e.message, 'error');
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

/**
 * Aplica os dados de um template ao editor, recriando os componentes.
 */
function applyTemplateData(td) {
    // 1. Resolução
    if (td.resolution) {
        state.resolution = td.resolution;
        document.getElementById('resolution').value = td.resolution;
        document.querySelectorAll('.res-chip').forEach(c => {
            c.classList.toggle('active', c.dataset.res === td.resolution);
        });
        const canvas = document.getElementById('previewCanvas');
        const [w, h] = td.resolution.split('x').map(Number);
        canvas.style.aspectRatio = `${w}/${h}`;
    }

    // 2. Limpar tudo antes de recriar
    _clearAllSections();

    // 3. Recriar áudios (slots vazios)
    const audioSlots = td.audio_slots || [];
    const audioCount = Math.max(audioSlots.length, 1);
    for (let i = 0; i < audioCount; i++) {
        addAudioItem();
        if (audioSlots[i]) {
            const items = document.querySelectorAll('#audioItemsList .audio-item');
            const item = items[items.length - 1];
            const slot = audioSlots[i];
            // Setar tipo
            if (slot.type === 'omni') {
                const omniTab = item.querySelector('.audio-tab:nth-child(2)');
                if (omniTab) switchAudioType(omniTab, 'omni');
            }
            // Setar volume
            const activePanel = item.querySelector('.audio-panel.active');
            const volRange = activePanel?.querySelector('.audio-vol-range');
            if (volRange && slot.volume !== undefined) {
                volRange.value = slot.volume;
                const display = volRange.nextElementSibling;
                if (display) display.textContent = slot.volume + '%';
            }
        }
    }

    // 4. Recriar backgrounds
    const bgSegs = td.bg_segments || [];
    const bgCount = Math.max(bgSegs.length, 1);
    for (let i = 0; i < bgCount; i++) {
        addBgSegment();
        if (bgSegs[i]) {
            const segs = document.querySelectorAll('#bgSegmentsList .img-segment');
            const seg = segs[segs.length - 1];
            const data = bgSegs[i];
            const startInput = seg.querySelector('.seg-start');
            const endInput = seg.querySelector('.seg-end');
            if (startInput && data.start_sec !== undefined && data.start_sec !== null) startInput.value = data.start_sec;
            if (endInput && data.end_sec !== undefined && data.end_sec !== null) endInput.value = data.end_sec;
        }
    }

    // 5. Recriar overlays
    const ovSegs = td.overlay_segments || [];
    for (const ovData of ovSegs) {
        addOverlaySegment();
        const segs = document.querySelectorAll('#overlaySegmentsList .img-segment');
        const seg = segs[segs.length - 1];
        const startInput = seg.querySelector('.seg-start');
        const endInput = seg.querySelector('.seg-end');
        if (startInput && ovData.start_sec !== undefined && ovData.start_sec !== null) startInput.value = ovData.start_sec;
        if (endInput && ovData.end_sec !== undefined && ovData.end_sec !== null) endInput.value = ovData.end_sec;

        // Posição
        if (ovData.position) {
            seg.querySelectorAll('.overlay-pos-grid button').forEach(b => {
                b.classList.toggle('active', b.dataset.pos === ovData.position);
            });
        }
        // Scale
        const scaleRange = seg.querySelector('.overlay-scale-range');
        if (scaleRange && ovData.scale !== undefined) {
            scaleRange.value = ovData.scale;
            const scaleDisplay = scaleRange.nextElementSibling;
            if (scaleDisplay) scaleDisplay.textContent = ovData.scale + '%';
        }
        // Controle fino em px
        if (ovData.px_width !== undefined && ovData.px_width !== null) {
            const pxW = seg.querySelector('.overlay-px-w');
            if (pxW) pxW.value = ovData.px_width;
        }
        if (ovData.px_height !== undefined && ovData.px_height !== null) {
            const pxH = seg.querySelector('.overlay-px-h');
            if (pxH) pxH.value = ovData.px_height;
        }
        if (ovData.px_x !== undefined && ovData.px_x !== null) {
            const pxX = seg.querySelector('.overlay-px-x');
            if (pxX) pxX.value = ovData.px_x;
        }
        if (ovData.px_y !== undefined && ovData.px_y !== null) {
            const pxY = seg.querySelector('.overlay-px-y');
            if (pxY) pxY.value = ovData.px_y;
        }
    }

    // 6. Recriar textos sobrepostos
    const textOverlays = td.text_overlays || [];
    for (const txt of textOverlays) {
        addTextOverlay();
        const items = document.querySelectorAll('#textOverlaysList .text-overlay-item');
        const item = items[items.length - 1];
        const content = item.querySelector('.text-content');
        if (content && txt.text) content.value = txt.text;

        // Fonte: buscar a key pelo path do font file
        const fontSelect = item.querySelector('.text-font');
        if (fontSelect && txt.font) {
            // Procurar no FONT_FAMILY_MAP qual key tem esse file
            for (const [key, family] of Object.entries(FONT_FAMILY_MAP)) {
                if (Object.values(family).includes(txt.font)) {
                    fontSelect.value = key;
                    break;
                }
            }
        }

        const sizeInput = item.querySelector('.text-size');
        if (sizeInput && txt.size) sizeInput.value = txt.size;

        const colorInput = item.querySelector('.text-color');
        const colorLabel = item.querySelector('.text-color-label');
        if (colorInput && txt.color) {
            colorInput.value = txt.color;
            if (colorLabel) {
                colorLabel.textContent = txt.color.toUpperCase();
                colorLabel.style.color = txt.color;
            }
        }

        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        if (startInput && txt.start_sec !== undefined && txt.start_sec !== null) startInput.value = txt.start_sec;
        if (endInput && txt.end_sec !== undefined && txt.end_sec !== null) endInput.value = txt.end_sec;

        // Posição
        if (txt.position) {
            item.querySelectorAll('.text-pos-grid button').forEach(b => {
                b.classList.toggle('active', b.dataset.pos === txt.position);
            });
        }

        // Px fino
        if (txt.px_x !== undefined && txt.px_x !== null) {
            const pxX = item.querySelector('.text-px-x');
            if (pxX) pxX.value = txt.px_x;
        }
        if (txt.px_y !== undefined && txt.px_y !== null) {
            const pxY = item.querySelector('.text-px-y');
            if (pxY) pxY.value = txt.px_y;
        }
    }

    // 7. Animações (selecionar na galeria)
    const animations = td.animations || [];
    state.selectedAnimations = [];
    document.querySelectorAll('#animationsCtrlList .effect-ctrl-item').forEach(el => el.remove());
    for (const anim of animations) {
        // Selecionar na galeria
        const galleryItem = document.querySelector(`#animationsGallery .gallery-item[data-name="${anim.name}"]`);
        if (galleryItem && !galleryItem.classList.contains('selected')) {
            galleryItem.click();
        }
        // Aplicar settings ao painel de controle
        const ctrlItem = document.querySelector(`#animationsCtrlList .effect-ctrl-item[data-effect-name="${anim.name}"]`);
        if (ctrlItem) {
            const fullCheck = ctrlItem.querySelector('.effect-full-video');
            if (fullCheck && anim.full_video !== undefined) fullCheck.checked = anim.full_video;
            const startInput = ctrlItem.querySelector('.effect-start');
            const endInput = ctrlItem.querySelector('.effect-end');
            if (startInput && anim.start_sec !== undefined && anim.start_sec !== null) startInput.value = anim.start_sec;
            if (endInput && anim.end_sec !== undefined && anim.end_sec !== null) endInput.value = anim.end_sec;
            const intensityRange = ctrlItem.querySelector('.effect-intensity');
            if (intensityRange && anim.intensity !== undefined) {
                intensityRange.value = anim.intensity;
                const display = intensityRange.nextElementSibling;
                if (display) display.textContent = anim.intensity + '%';
            }
        }
    }

    // 8. Elementos (selecionar na galeria)
    const elements = td.elements || [];
    state.selectedElements = [];
    document.querySelectorAll('#elementsCtrlList .effect-ctrl-item').forEach(el => el.remove());
    for (const elem of elements) {
        const galleryItem = document.querySelector(`#elementsGallery .gallery-item[data-name="${elem.name}"]`);
        if (galleryItem && !galleryItem.classList.contains('selected')) {
            galleryItem.click();
        }
        const ctrlItem = document.querySelector(`#elementsCtrlList .effect-ctrl-item[data-effect-name="${elem.name}"]`);
        if (ctrlItem) {
            const fullCheck = ctrlItem.querySelector('.effect-full-video');
            if (fullCheck && elem.full_video !== undefined) fullCheck.checked = elem.full_video;
            const startInput = ctrlItem.querySelector('.effect-start');
            const endInput = ctrlItem.querySelector('.effect-end');
            if (startInput && elem.start_sec !== undefined && elem.start_sec !== null) startInput.value = elem.start_sec;
            if (endInput && elem.end_sec !== undefined && elem.end_sec !== null) endInput.value = elem.end_sec;
        }
    }

    // 9. Animações customizadas (slots vazios)
    const customAnims = td.custom_anims || [];
    for (const ca of customAnims) {
        addCustomAnim();
        const items = document.querySelectorAll('#customAnimsList .custom-anim-item');
        const item = items[items.length - 1];
        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        if (startInput && ca.start_sec !== undefined && ca.start_sec !== null) startInput.value = ca.start_sec;
        if (endInput && ca.end_sec !== undefined && ca.end_sec !== null) endInput.value = ca.end_sec;

        if (ca.position) {
            item.querySelectorAll('.custom-anim-pos-grid button').forEach(b => {
                b.classList.toggle('active', b.dataset.pos === ca.position);
            });
        }
        const scaleRange = item.querySelector('.custom-anim-scale');
        if (scaleRange && ca.scale !== undefined) {
            scaleRange.value = ca.scale;
            const scaleDisplay = scaleRange.nextElementSibling;
            if (scaleDisplay) scaleDisplay.textContent = ca.scale + '%';
        }
        const loopCheck = item.querySelector('.custom-anim-loop');
        if (loopCheck && ca.loop !== undefined) loopCheck.checked = ca.loop;
    }

    // 10. Áudios secundários (slots vazios)
    const secAudios = td.sec_audios || [];
    for (const sa of secAudios) {
        addSecAudio();
        const items = document.querySelectorAll('#secAudioList .sec-audio-item');
        const item = items[items.length - 1];
        const volRange = item.querySelector('.sec-audio-vol');
        const volDisplay = item.querySelector('.sec-audio-vol-display');
        if (volRange && sa.volume !== undefined) {
            volRange.value = sa.volume;
            if (volDisplay) volDisplay.textContent = sa.volume + '%';
        }
        const startInput = item.querySelector('.seg-start');
        const endInput = item.querySelector('.seg-end');
        if (startInput && sa.start_sec !== undefined && sa.start_sec !== null) startInput.value = sa.start_sec;
        if (endInput && sa.end_sec !== undefined && sa.end_sec !== null) endInput.value = sa.end_sec;
        const loopCheck = item.querySelector('.sec-audio-loop');
        if (loopCheck && sa.loop !== undefined) loopCheck.checked = sa.loop;
    }

    // 11. Camadas
    if (td.layers && td.layers.length) {
        state.layers = td.layers;
        renderLayers();
    } else {
        updateLayers();
    }

    refreshTimelineUI();
    refreshPreviewNow();
}

/**
 * Limpa todos os itens do editor (para poder recriar do template).
 */
function _clearAllSections() {
    // Áudios
    document.querySelectorAll('#audioItemsList .audio-item').forEach(item => {
        if (item._omniEventSource) { item._omniEventSource.close(); item._omniEventSource = null; }
        const audioEl = item.querySelector('.audio-preview-el');
        if (audioEl && audioEl.src && audioEl.src.startsWith('blob:')) URL.revokeObjectURL(audioEl.src);
        item.remove();
    });
    audioItemCounter = 0;

    // Backgrounds
    document.querySelectorAll('#bgSegmentsList .img-segment').forEach(s => s.remove());
    bgSegmentCounter = 0;

    // Overlays
    document.querySelectorAll('#overlaySegmentsList .img-segment').forEach(s => s.remove());
    overlaySegmentCounter = 0;

    // Textos
    document.querySelectorAll('#textOverlaysList .text-overlay-item').forEach(s => s.remove());
    textOverlayCounter = 0;

    // Animações customizadas
    document.querySelectorAll('#customAnimsList .custom-anim-item').forEach(s => s.remove());
    customAnimCounter = 0;

    // Áudios secundários
    document.querySelectorAll('#secAudioList .sec-audio-item').forEach(s => s.remove());
    secAudioCounter = 0;

    // Animações e elementos da galeria
    state.selectedAnimations = [];
    state.selectedElements = [];
    document.querySelectorAll('#animationsGallery .gallery-item.selected').forEach(g => g.classList.remove('selected'));
    document.querySelectorAll('#elementsGallery .gallery-item.selected').forEach(g => g.classList.remove('selected'));
    document.querySelectorAll('#animationsCtrlList .effect-ctrl-item').forEach(el => el.remove());
    document.querySelectorAll('#elementsCtrlList .effect-ctrl-item').forEach(el => el.remove());
}

// ══════════════════════════════════════════
// Submit: Scene Mode
// ══════════════════════════════════════════

/**
 * Submit em modo cenas — resolve a timeline e envia tempos absolutos ao backend.
 */
async function submitCompositorSceneMode(btn, title) {
    // Validar que existem cenas com pelo menos 1 elemento
    const totalElements = state.scenes.reduce((sum, s) => sum + s.elements.length, 0);
    if (totalElements === 0) {
        showToast('Adicione pelo menos um elemento a uma cena.', 'error');
        return;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Resolvendo timeline...';

    // Resolver timeline
    resolveAndRefreshTimeline();
    const scenesData = collectScenesForSubmit();
    if (!scenesData) {
        showToast('Erro ao resolver a timeline.', 'error');
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
        return;
    }

    btn.textContent = '⏳ Enviando...';

    const formData = new FormData();
    formData.set('title', title);
    formData.set('resolution', state.resolution);

    // Metadados JSON resolvidos
    formData.set('audio_items_json', JSON.stringify(scenesData.audioItems));
    formData.set('bg_segments_json', JSON.stringify(scenesData.bgSegments));
    formData.set('overlay_segments_json', JSON.stringify(scenesData.overlaySegments));
    formData.set('animations_json', JSON.stringify([]));
    formData.set('elements_json', JSON.stringify([]));
    formData.set('custom_anims_json', JSON.stringify(scenesData.customAnims || []));
    formData.set('text_overlays_json', JSON.stringify(scenesData.textOverlays));
    formData.set('sec_audios_json', JSON.stringify(scenesData.secAudios));
    formData.set('layers_json', JSON.stringify(state.layers || []));

    // Coletar arquivos dos elementos de cena
    let audioFileIdx = 0;
    let bgFileIdx = 0;
    let ovFileIdx = 0;
    let saFileIdx = 0;
    let caFileIdx = 0;

    for (const scene of state.scenes) {
        for (const el of scene.elements) {
            const fileInput = document.querySelector(`.scene-element-file[data-element-id="${el.id}"]`);

            if (el.type === 'background') {
                if (fileInput && fileInput.files[0]) {
                    formData.append(`bg_image_${bgFileIdx}`, fileInput.files[0]);
                }
                bgFileIdx++;
            } else if (el.type === 'audio') {
                const elementDiv = document.querySelector(`.scene-element[data-element-id="${el.id}"]`);
                const activePanel = elementDiv?.querySelector('.audio-panel.active');
                const panelType = activePanel ? activePanel.dataset.panelType : 'upload';

                if (panelType === 'upload') {
                    if (fileInput && fileInput.files[0]) {
                        formData.append(`audio_file_${audioFileIdx}`, fileInput.files[0]);
                    }
                } else if (panelType === 'omni') {
                    if (elementDiv && elementDiv._omniGenerated && elementDiv._omniGenerated.blob) {
                        formData.append(`audio_file_${audioFileIdx}`, elementDiv._omniGenerated.blob, `omni_audio_${audioFileIdx}.wav`);
                    }
                }
                audioFileIdx++;
            } else if (el.type === 'overlay') {
                if (fileInput && fileInput.files[0]) {
                    formData.append(`overlay_image_${ovFileIdx}`, fileInput.files[0]);
                }
                ovFileIdx++;
            } else if (el.type === 'secondary_audio') {
                if (fileInput && fileInput.files[0]) {
                    formData.append(`sec_audio_file_${saFileIdx}`, fileInput.files[0]);
                }
                saFileIdx++;
            } else if (el.type === 'custom_anim') {
                if (fileInput && fileInput.files[0]) {
                    formData.append(`custom_anim_${caFileIdx}`, fileInput.files[0]);
                }
                caFileIdx++;
            }
        }
    }

    try {
        const response = await fetch('/video-compositor/render', { method: 'POST', body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Erro ao enviar');
        
        showToast(`Vídeo "${title}" enviado com sucesso!`, 'success');
        addToQueue(data.job_id, title);
        
        document.getElementById('title').value = '';
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
    } catch (err) {
        showToast(err.message, 'error');
        btn.disabled = false;
        btn.textContent = '🚀 Gerar Vídeo';
    }
}

// ══════════════════════════════════════════
// Modo Cenas — Timeline Dinâmica por Eventos
// ══════════════════════════════════════════

let sceneCounter = 0;

// ══════════════════════════════════════════
// Gerenciamento de Presets Customizados de Cena
// ══════════════════════════════════════════

/**
 * Renderiza o painel de presets de cenas (padrões + customizados).
 */
function renderPresetSelector() {
    const container = document.getElementById('presetSelector');
    if (!container) return;

    // Presets padrão
    const defaultPresets = [
        { key: 'quiz_question', name: 'Pergunta Quiz', icon: '❓', desc: 'Fundo + narração + timer + resposta' },
        { key: 'intro', name: 'Intro / Abertura', icon: '🎬', desc: 'Fundo + logo + narração + SFX' },
        { key: 'answer_reveal', name: 'Revelação', icon: '🎯', desc: 'Resposta + destaque + narração' },
        { key: 'simple', name: 'Simples', icon: '📄', desc: 'Fundo + narração' },
        { key: 'empty', name: 'Vazia', icon: '🆕', desc: 'Monte do zero' },
    ];

    // Presets do usuário
    const customPresets = JSON.parse(localStorage.getItem('custom_scene_presets') || '{}');

    let html = defaultPresets.map(p => `
        <div class="preset-card" onclick="addSceneFromPreset('${p.key}')">
            <span class="pc-icon">${p.icon}</span>
            <div class="pc-name">${p.name}</div>
            <div class="pc-desc">${p.desc}</div>
        </div>
    `).join('');

    // Adicionar presets salvos
    for (const [key, p] of Object.entries(customPresets)) {
        html += `
            <div class="preset-card" style="border-color: rgba(124,77,255,.3); position:relative;" onclick="addSceneFromPreset('${key}')">
                <span class="pc-icon">💾</span>
                <div class="pc-name">${escapeHtml(p.name)}</div>
                <div class="pc-desc">${escapeHtml(p.description)}</div>
                <button type="button" class="sc-btn-danger" style="position:absolute; top:4px; right:4px; border:none; background:none; color:#ef4444; font-size:.78rem; cursor:pointer;" onclick="event.stopPropagation(); deleteCustomScenePreset('${key}')" title="Excluir preset">✕</button>
            </div>
        `;
    }

    container.innerHTML = html;
}

/**
 * Salva a cena atual como preset.
 */
function saveSceneAsPreset(sceneId) {
    const scene = (state.scenes || []).find(s => s.scene_id === sceneId);
    if (!scene) return;

    const presetName = prompt('Nome do preset da cena:', scene.name.replace(/#\d+/, ''));
    if (!presetName) return;

    // Limpar IDs e mapear parasuffixes dinâmicos
    const elementsTemplate = scene.elements.map(el => {
        const suffix = el.id.split('_').slice(-1)[0] || el.id_suffix;
        return {
            id_suffix: suffix,
            label: el.label,
            type: el.type,
            trigger: el.trigger,
            end_mode: el.end_mode,
            z_level: el.z_level,
            properties: JSON.parse(JSON.stringify(el.properties || {})),
        };
    });

    const customPresets = JSON.parse(localStorage.getItem('custom_scene_presets') || '{}');
    const key = `custom_${Date.now()}`;
    customPresets[key] = {
        name: `💾 ${presetName}`,
        description: 'Preset salvo por você',
        elements: elementsTemplate,
    };

    localStorage.setItem('custom_scene_presets', JSON.stringify(customPresets));
    showToast(`Preset "${presetName}" salvo com sucesso!`, 'success');

    renderPresetSelector();
}

/**
 * Exclui um preset customizado.
 */
function deleteCustomScenePreset(presetKey) {
    if (!confirm('Excluir este preset de cena permanentemente?')) return;
    const customPresets = JSON.parse(localStorage.getItem('custom_scene_presets') || '{}');
    delete customPresets[presetKey];
    localStorage.setItem('custom_scene_presets', JSON.stringify(customPresets));
    showToast('Preset excluído!', 'info');
    renderPresetSelector();
}

/**
 * Alterna entre modo Clássico e modo Cenas.
 */
function switchEditorMode(btn, mode) {
    document.querySelectorAll('.mode-chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');

    const classicEl = document.getElementById('classicMode');
    const scenesEl = document.getElementById('scenesMode');

    if (mode === 'classic') {
        classicEl.classList.add('active');
        scenesEl.classList.remove('active');
        state.useEventTimeline = false;
    } else {
        classicEl.classList.remove('active');
        scenesEl.classList.add('active');
        state.useEventTimeline = true;
    }
}

/**
 * Adiciona uma cena a partir de um preset.
 */
function addSceneFromPreset(presetKey) {
    sceneCounter++;
    let sceneConfig;
    
    // Verificar se é preset customizado do localStorage
    const customPresets = JSON.parse(localStorage.getItem('custom_scene_presets') || '{}');
    if (customPresets[presetKey]) {
        const preset = customPresets[presetKey];
        const sceneId = `scene_${sceneCounter}_${Date.now().toString(36)}`;
        const elements = (preset.elements || []).map((el, i) => ({
            ...el,
            id: `${sceneId}_${el.id_suffix || i}`,
            scene_id: sceneId,
        }));
        sceneConfig = {
            scene_id: sceneId,
            name: `${preset.name.replace('💾 ', '')} #${sceneCounter}`,
            description: preset.description,
            preset_key: presetKey,
            elements,
        };
    } else {
        sceneConfig = instantiatePreset(presetKey, sceneCounter);
    }

    if (!state.scenes) state.scenes = [];
    state.scenes.push(sceneConfig);

    renderScene(sceneConfig, state.scenes.length - 1);
    resolveAndRefreshTimeline();
    showToast(`Cena "${sceneConfig.name}" adicionada!`, 'success');
}

/**
 * Renderiza um card de cena no DOM.
 */
function renderScene(sceneConfig, index) {
    const container = document.getElementById('scenesList');
    if (!container) return;

    const card = document.createElement('div');
    card.className = 'scene-card';
    card.dataset.sceneId = sceneConfig.scene_id;

    const elemCount = sceneConfig.elements.length;

    card.innerHTML = `
        <div class="scene-card-header" onclick="toggleSceneCard(this)">
            <span class="scene-chevron">▼</span>
            <div class="scene-card-num">${index + 1}</div>
            <span class="scene-card-name">${escapeHtml(sceneConfig.name)}</span>
            <span class="scene-card-badge">${elemCount} elemento${elemCount !== 1 ? 's' : ''}</span>
            <div class="scene-card-actions" onclick="event.stopPropagation()">
                <button type="button" title="Mover para cima" onclick="moveScene('${sceneConfig.scene_id}', -1)">⬆️</button>
                <button type="button" title="Mover para baixo" onclick="moveScene('${sceneConfig.scene_id}', 1)">⬇️</button>
                <button type="button" title="Duplicar cena" onclick="duplicateScene('${sceneConfig.scene_id}')">📋</button>
                <button type="button" title="Salvar como Preset" onclick="saveSceneAsPreset('${sceneConfig.scene_id}')">💾</button>
                <button type="button" class="sc-btn-danger" title="Remover cena" onclick="removeScene('${sceneConfig.scene_id}')">🗑️</button>
            </div>
        </div>
        <div class="scene-card-body">
            <div class="scene-elements-list" data-scene-id="${sceneConfig.scene_id}"></div>
            <div style="position:relative; display:inline-block;">
                <button type="button" class="add-element-btn" onclick="toggleAddElementDropdown(this, '${sceneConfig.scene_id}')">
                    ➕ Adicionar Elemento
                </button>
            </div>
        </div>
    `;

    container.appendChild(card);

    // Renderizar elementos
    const elemList = card.querySelector('.scene-elements-list');
    for (const el of sceneConfig.elements) {
        renderSceneElement(elemList, el, sceneConfig);
    }
}

/**
 * Renderiza um elemento dentro de uma cena.
 */
function renderSceneElement(container, elementConfig, sceneConfig) {
    const tpl = document.getElementById('tplSceneElement').content.cloneNode(true);
    const el = tpl.querySelector('.scene-element');
    el.dataset.elementId = elementConfig.id;

    if (elementConfig.type === 'audio') {
        el.classList.add('audio-item');
        el._omniGenerated = null;
        el._omniEventSource = null;
    }

    // Icon por tipo
    const icons = {
        background: '🖼️', audio: '🎵', overlay: '📸',
        text: '📝', secondary_audio: '🎶',
        animation: '✨', custom_anim: '🎞️',
    };
    const typeLabels = {
        background: 'Fundo', audio: 'Áudio', overlay: 'Sobreposta',
        text: 'Texto', secondary_audio: 'Áudio Sec.',
        animation: 'Animação', custom_anim: 'GIF/Vídeo',
    };

    el.querySelector('.scene-element-icon').textContent = icons[elementConfig.type] || '📦';
    el.querySelector('.scene-element-label').textContent = elementConfig.label || elementConfig.id;
    const typeBadge = el.querySelector('.scene-element-type');
    typeBadge.textContent = typeLabels[elementConfig.type] || elementConfig.type;
    typeBadge.classList.add(elementConfig.type === 'background' ? 'bg' : elementConfig.type);

    // Populate trigger event dropdown
    const triggerSelect = el.querySelector('.trigger-event');
    const engine = new TimelineEngine();
    engine.scenes = state.scenes || [];
    const availableEvents = engine.getAvailableEvents(sceneConfig.scene_id, elementConfig.id);
    triggerSelect.innerHTML = availableEvents.map(e =>
        `<option value="${e.value}"${elementConfig.trigger?.event === e.value ? ' selected' : ''}>${e.label}</option>`
    ).join('');

    // Offset
    const offsetInput = el.querySelector('.trigger-offset');
    offsetInput.value = elementConfig.trigger?.offset || 0;

    // End mode
    const endModeSelect = el.querySelector('.end-mode-select');
    const endMode = elementConfig.end_mode;
    if (typeof endMode === 'string') {
        endModeSelect.value = endMode;
    } else if (endMode && endMode.duration !== undefined) {
        endModeSelect.value = 'duration';
    } else if (endMode && endMode.event) {
        endModeSelect.value = 'event';
    }

    // End mode extra fields
    _populateEndModeExtra(el, elementConfig, sceneConfig);

    // Z-Level
    const zInput = el.querySelector('.z-level-input');
    zInput.value = elementConfig.z_level || 0;

    // Content area (file drops, text inputs etc.)
    const contentArea = el.querySelector('.scene-element-content');
    _renderElementContent(contentArea, elementConfig);

    // Event listeners para triggers e modo de fim
    triggerSelect.addEventListener('change', () => {
        elementConfig.trigger.event = triggerSelect.value;
        resolveAndRefreshTimeline();
    });
    offsetInput.addEventListener('change', () => {
        elementConfig.trigger.offset = parseFloat(offsetInput.value) || 0;
        resolveAndRefreshTimeline();
    });
    endModeSelect.addEventListener('change', () => {
        onEndModeChange(endModeSelect);
    });
    zInput.addEventListener('change', () => {
        elementConfig.z_level = parseInt(zInput.value) || 0;
        resolveAndRefreshTimeline();
    });

    // Exportar Eventos
    const exportCheck = el.querySelector('.export-events-check');
    if (exportCheck) {
        exportCheck.checked = elementConfig.export_events || false;
        exportCheck.addEventListener('change', () => {
            elementConfig.export_events = exportCheck.checked;
            resolveAndRefreshTimeline();
        });
    }

    container.appendChild(el);
}

/**
 * Popula campos extras do end mode (duração fixa, evento de fim).
 */
function _populateEndModeExtra(el, elementConfig, sceneConfig) {
    const extra = el.querySelector('.end-mode-extra');
    const endMode = elementConfig.end_mode;

    if (typeof endMode === 'object' && endMode.duration !== undefined) {
        extra.innerHTML = `
            <label>Duração (s)</label>
            <input type="number" class="end-duration-input" step="0.1" min="0.1" value="${endMode.duration}" placeholder="5.0">
        `;
        const durInput = extra.querySelector('.end-duration-input');
        durInput.addEventListener('change', () => {
            elementConfig.end_mode = { duration: parseFloat(durInput.value) || 5 };
            resolveAndRefreshTimeline();
        });
    } else if (typeof endMode === 'object' && endMode.event) {
        const engine = new TimelineEngine();
        engine.scenes = state.scenes || [];
        const events = engine.getAvailableEvents(sceneConfig.scene_id, elementConfig.id);
        extra.innerHTML = `
            <label>Evento de Fim</label>
            <select class="end-event-select">
                ${events.map(e => `<option value="${e.value}"${endMode.event === e.value ? ' selected' : ''}>${e.label}</option>`).join('')}
            </select>
        `;
        const evtSelect = extra.querySelector('.end-event-select');
        evtSelect.addEventListener('change', () => {
            elementConfig.end_mode = { event: evtSelect.value, offset: 0 };
            resolveAndRefreshTimeline();
        });
    } else {
        extra.innerHTML = '';
    }
}

/**
 * Renderiza o conteúdo específico de um elemento (file drop, textarea etc.)
 */
function _renderElementContent(container, elementConfig) {
    const type = elementConfig.type;
    if (!elementConfig.properties) elementConfig.properties = {};
    const props = elementConfig.properties;

    if (type === 'background' || type === 'overlay' || type === 'custom_anim') {
        let accept = 'image/*';
        let label = '📁 Imagem de fundo';
        if (type === 'overlay') label = '📸 Imagem sobreposta';
        if (type === 'custom_anim') {
            accept = 'video/*,image/gif,image/webp,image/apng';
            label = '🎞️ Vídeo ou GIF Animado';
        }

        container.innerHTML = `
            <div class="scene-file-drop">
                <input type="file" accept="${accept}" class="scene-element-file" data-element-id="${elementConfig.id}">
                <div class="sfd-label">${label}</div>
                <div class="sfd-hint">PNG, JPG, WEBP${type === 'custom_anim' ? ', GIF, MP4' : ''}</div>
                <div class="file-name"></div>
                <img class="preview" alt="" style="display:none; max-width:100%; border-radius:6px; margin-top:8px;">
            </div>
        `;
        const fileInput = container.querySelector('.scene-element-file');
        const fileName = container.querySelector('.file-name');
        const preview = container.querySelector('.preview');

        fileInput.addEventListener('change', () => {
            if (fileInput.files[0]) {
                fileName.textContent = '✅ ' + fileInput.files[0].name;
                fileName.style.display = 'block';
                if (!fileInput.files[0].type.startsWith('video/')) {
                    const reader = new FileReader();
                    reader.onload = ev => {
                        preview.src = ev.target.result;
                        preview.style.display = 'block';
                        preview.onload = () => {
                            if (type === 'overlay' || type === 'custom_anim') {
                                _syncFineFromQuickForSceneElement(container, props);
                            }
                            refreshPreviewNow();
                        };
                    };
                    reader.readAsDataURL(fileInput.files[0]);
                } else {
                    preview.style.display = 'none';
                    refreshPreviewNow();
                }
            }
        });

        // Controles de Transição para Background
        if (type === 'background') {
            container.insertAdjacentHTML('beforeend', `
                <div style="margin-top:8px;">
                    <label style="font-size:.75rem;">Efeito de Transição (Entrada)</label>
                    <select class="scene-element-transition" style="width: 100%;">
                        <option value="none" ${props.transition === 'none' ? 'selected' : ''}>Seco</option>
                        <option value="fade" ${props.transition === 'fade' ? 'selected' : ''}>Esmaecer (Fade)</option>
                    </select>
                </div>
            `);
            const transSelect = container.querySelector('.scene-element-transition');
            transSelect.addEventListener('change', () => {
                props.transition = transSelect.value;
            });
        }

        // Controles de Posição, Escala e Transição para Overlay e Custom Anim
        if (type === 'overlay' || type === 'custom_anim') {
            container.insertAdjacentHTML('beforeend', `
                <div style="margin-top:8px;">
                    <label style="font-size:.75rem;">Posição rápida</label>
                    <div class="position-grid overlay-pos-grid" style="max-width:180px;">
                        <button type="button" data-pos="superior esquerda" class="${props.position === 'superior esquerda' ? 'active' : ''}">↖</button>
                        <button type="button" data-pos="superior" class="${props.position === 'superior' ? 'active' : ''}">↑</button>
                        <button type="button" data-pos="superior direita" class="${props.position === 'superior direita' ? 'active' : ''}">↗</button>
                        <button type="button" data-pos="esquerda" class="${props.position === 'esquerda' ? 'active' : ''}">←</button>
                        <button type="button" data-pos="centro" class="${(!props.position || props.position === 'centro') ? 'active' : ''}">●</button>
                        <button type="button" data-pos="direita" class="${props.position === 'direita' ? 'active' : ''}">→</button>
                        <button type="button" data-pos="inferior esquerda" class="${props.position === 'inferior esquerda' ? 'active' : ''}">↙</button>
                        <button type="button" data-pos="inferior" class="${props.position === 'inferior' ? 'active' : ''}">↓</button>
                        <button type="button" data-pos="inferior direita" class="${props.position === 'inferior direita' ? 'active' : ''}">↘</button>
                    </div>
                    <div class="volume-control" style="margin-top:6px;">
                        <label>📐 Tamanho</label>
                        <input type="range" min="5" max="100" value="${props.scale || (type === 'custom_anim' ? 30 : 50)}" class="overlay-scale-range">
                        <span class="vol-value">${props.scale || (type === 'custom_anim' ? 30 : 50)}%</span>
                    </div>
                    <div style="margin-top:8px;">
                        <label style="font-size:.75rem;">Efeito de Transição (Entrada)</label>
                        <select class="scene-element-transition" style="width: 100%;">
                            <option value="none" ${props.transition === 'none' ? 'selected' : ''}>Seco</option>
                            <option value="fade" ${props.transition === 'fade' ? 'selected' : ''}>Esmaecer (Fade)</option>
                            <option value="slide_left" ${props.transition === 'slide_left' ? 'selected' : ''}>Deslizar da Esquerda</option>
                            <option value="slide_right" ${props.transition === 'slide_right' ? 'selected' : ''}>Deslizar da Direita</option>
                            <option value="slide_up" ${props.transition === 'slide_up' ? 'selected' : ''}>Deslizar de Baixo</option>
                            <option value="slide_down" ${props.transition === 'slide_down' ? 'selected' : ''}>Deslizar de Cima</option>
                        </select>
                    </div>

                    <!-- Controle fino: tamanho em px e posição X, Y -->
                    <details class="overlay-fine-ctrl" style="margin-top:10px; border:1px solid rgba(255,255,255,.1); border-radius:10px; padding:8px 12px;">
                        <summary style="cursor:pointer; font-weight:600; font-size:.85rem; user-select:none;">
                            🎯 Controle fino (pixels)
                        </summary>
                        <p class="hint" style="margin:6px 0 10px; font-size:.7rem; opacity:.7;">Baseado na resolução de saída. Deixe em branco para usar os controles rápidos.</p>
                        <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;">
                            <div>
                                <label style="font-size:.7rem;">Largura (px)</label>
                                <input type="number" class="overlay-px-w" min="1" step="1" placeholder="auto" value="${props.px_width || ''}" style="padding:4px; font-size:.78rem; width:100%;">
                            </div>
                            <div>
                                <label style="font-size:.7rem;">Altura (px)</label>
                                <input type="number" class="overlay-px-h" min="1" step="1" placeholder="auto" value="${props.px_height || ''}" style="padding:4px; font-size:.78rem; width:100%;">
                            </div>
                            <div>
                                <label style="font-size:.7rem;">Posição X (px)</label>
                                <input type="number" class="overlay-px-x" step="1" placeholder="(centro)" value="${props.px_x !== undefined && props.px_x !== null ? props.px_x : ''}" style="padding:4px; font-size:.78rem; width:100%;">
                            </div>
                            <div>
                                <label style="font-size:.7rem;">Posição Y (px)</label>
                                <input type="number" class="overlay-px-y" step="1" placeholder="(centro)" value="${props.px_y !== undefined && props.px_y !== null ? props.px_y : ''}" style="padding:4px; font-size:.78rem; width:100%;">
                            </div>
                        </div>
                        <button type="button" class="vc-btn vc-btn-primary vc-btn-sm overlay-apply-btn" style="width:100%; font-size:.75rem; padding:4px;">
                            ▶ Aplicar ao preview
                        </button>
                    </details>
                </div>
            `);

            // Loop para Custom Anim
            if (type === 'custom_anim') {
                container.insertAdjacentHTML('beforeend', `
                    <label style="display:flex; align-items:center; gap:6px; margin-top:6px; font-size:.82rem;">
                        <input type="checkbox" class="custom-anim-loop" ${props.loop !== false ? 'checked' : ''} style="width:auto; accent-color:#e040fb;">
                        🔄 Loop
                    </label>
                `);
                const loopCheck = container.querySelector('.custom-anim-loop');
                loopCheck.addEventListener('change', () => {
                    props.loop = loopCheck.checked;
                });
            }

            // Grid Pos click listener
            const posGrid = container.querySelector('.overlay-pos-grid');
            posGrid.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    posGrid.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    props.position = btn.dataset.pos;
                    _syncFineFromQuickForSceneElement(container, props);
                    refreshPreviewNow();
                });
            });

            // Scale listener
            const scaleRange = container.querySelector('.overlay-scale-range');
            scaleRange.addEventListener('input', () => {
                scaleRange.nextElementSibling.textContent = scaleRange.value + '%';
                props.scale = parseInt(scaleRange.value);
                _syncFineFromQuickForSceneElement(container, props);
                refreshPreviewNow();
            });

            // Transition listener
            const transSelect = container.querySelector('.scene-element-transition');
            transSelect.addEventListener('change', () => {
                props.transition = transSelect.value;
            });

            // Controle fino listeners
            const pxWInput = container.querySelector('.overlay-px-w');
            const pxHInput = container.querySelector('.overlay-px-h');
            const pxXInput = container.querySelector('.overlay-px-x');
            const pxYInput = container.querySelector('.overlay-px-y');
            const applyBtn = container.querySelector('.overlay-apply-btn');

            const saveFineProps = () => {
                props.px_width = pxWInput.value.trim() !== '' ? parseInt(pxWInput.value) : null;
                props.px_height = pxHInput.value.trim() !== '' ? parseInt(pxHInput.value) : null;
                props.px_x = pxXInput.value.trim() !== '' ? parseInt(pxXInput.value) : null;
                props.px_y = pxYInput.value.trim() !== '' ? parseInt(pxYInput.value) : null;
            };

            [pxWInput, pxHInput, pxXInput, pxYInput].forEach(inp => {
                inp.addEventListener('change', saveFineProps);
                inp.addEventListener('input', saveFineProps);
            });

            applyBtn.addEventListener('click', () => {
                saveFineProps();
                refreshPreviewNow();
                showToast('Preview atualizado com controle fino!', 'success');
            });
        }
    } else if (type === 'audio' || type === 'secondary_audio') {
        if (type === 'audio') {
            container.innerHTML = `
                <div class="audio-tabs" style="margin-bottom:10px;">
                    <button type="button" class="audio-tab active" onclick="switchAudioType(this,'upload')">📁 Arquivo</button>
                    <button type="button" class="audio-tab" onclick="switchAudioType(this,'omni')">🤖 IA (OmniVoice)</button>
                </div>
                <div class="audio-panels-wrap"></div>
            `;
            const panelsWrap = container.querySelector('.audio-panels-wrap');

            const uploadTpl = document.getElementById('tplAudioUpload').content.cloneNode(true);
            const fileInp = uploadTpl.querySelector('.audio-file-input');
            if (fileInp) {
                fileInp.className = 'scene-element-file';
                fileInp.dataset.elementId = elementConfig.id;
            }
            panelsWrap.appendChild(uploadTpl);

            const omniTpl = document.getElementById('tplAudioOmni').content.cloneNode(true);
            const omniPanel = omniTpl.querySelector('.audio-panel');
            omniPanel.classList.remove('active');
            panelsWrap.appendChild(omniTpl);

            // Inicializar inputs e seletores do OmniVoice
            const wrapper = container.closest('.scene-element');
            const fileInput = wrapper.querySelector('.scene-element-file');
            const fileName = wrapper.querySelector('.audio-panel[data-panel-type=upload] .file-name');
            const uploadPanel = wrapper.querySelector('.audio-panel[data-panel-type=upload]');

            fileInput.addEventListener('change', () => {
                if (fileInput.files[0]) {
                    fileName.textContent = '✅ ' + fileInput.files[0].name;
                    fileName.style.display = 'block';
                    setupAudioPreviewFromFile(uploadPanel, fileInput.files[0]);

                    // Decodificação binária imediata para obter a duração exata do áudio
                    const file = fileInput.files[0];
                    const ctx = new (window.AudioContext || window.webkitAudioContext)();
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        ctx.decodeAudioData(e.target.result).then(buffer => {
                            const dur = buffer.duration;
                            if (isFinite(dur) && dur > 0) {
                                if (!state.sceneResourceDurations) state.sceneResourceDurations = {};
                                state.sceneResourceDurations[elementConfig.id] = dur;
                                resolveAndRefreshTimeline();
                            }
                        }).catch(err => {
                            console.warn("Erro ao decodificar áudio via AudioContext:", err);
                        });
                    };
                    reader.readAsArrayBuffer(file);
                }
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
        } else {
            // Secondary Audio
            container.innerHTML = `
                <div class="scene-file-drop">
                    <input type="file" accept="audio/*" class="scene-element-file" data-element-id="${elementConfig.id}">
                    <div class="sfd-label">🎵 Arquivo de áudio secundário</div>
                    <div class="sfd-hint">MP3, WAV, OGG</div>
                    <div class="file-name"></div>
                </div>
                <div class="audio-player-wrap" style="display:none; margin-top:8px;">
                    <div class="audio-player-header">
                        <span class="player-icon">🎧</span>
                        <span class="player-label">Preview</span>
                        <span class="player-duration"></span>
                    </div>
                    <audio controls preload="metadata" class="audio-preview-el scene-audio-preview"></audio>
                </div>
                <div class="volume-control" style="margin-top:6px;">
                    <label>🔈 Vol</label>
                    <input type="range" min="0" max="100" value="${props.volume || 20}" class="sec-audio-vol">
                    <span class="vol-value">${props.volume || 20}%</span>
                </div>
                <label style="display:flex; align-items:center; gap:6px; margin-top:6px; font-size:.82rem;">
                    <input type="checkbox" class="sec-audio-loop" ${props.loop !== false ? 'checked' : ''} style="width:auto; accent-color:#e040fb;">
                    🔄 Loop
                </label>
            `;

            const volRange = container.querySelector('.sec-audio-vol');
            const loopCheck = container.querySelector('.sec-audio-loop');

            volRange.addEventListener('input', () => {
                volRange.nextElementSibling.textContent = volRange.value + '%';
                props.volume = parseInt(volRange.value);
            });
            loopCheck.addEventListener('change', () => {
                props.loop = loopCheck.checked;
            });

            const fileInput = container.querySelector('.scene-element-file');
            const fileName = container.querySelector('.file-name');
            const playerWrap = container.querySelector('.audio-player-wrap');
            const audioEl = container.querySelector('.scene-audio-preview');
            const durationEl = container.querySelector('.player-duration');

            fileInput.addEventListener('change', () => {
                if (fileInput.files[0]) {
                    fileName.textContent = '✅ ' + fileInput.files[0].name;
                    fileName.style.display = 'block';
                    const url = URL.createObjectURL(fileInput.files[0]);
                    audioEl.src = url;
                    playerWrap.style.display = 'block';

                    // Decodificação binária imediata para obter a duração exata do áudio
                    const file = fileInput.files[0];
                    const ctx = new (window.AudioContext || window.webkitAudioContext)();
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        ctx.decodeAudioData(e.target.result).then(buffer => {
                            const dur = buffer.duration;
                            if (isFinite(dur) && dur > 0) {
                                durationEl.textContent = `${Math.floor(dur / 60)}:${Math.floor(dur % 60).toString().padStart(2, '0')}`;
                                if (!state.sceneResourceDurations) state.sceneResourceDurations = {};
                                state.sceneResourceDurations[elementConfig.id] = dur;
                                resolveAndRefreshTimeline();
                            }
                        }).catch(err => {
                            console.warn("Erro ao decodificar áudio secundário via AudioContext:", err);
                        });
                    };
                    reader.readAsArrayBuffer(file);
                }
            });
        }
    } else if (type === 'text') {
        container.innerHTML = `
            <textarea rows="2" class="scene-text-input" placeholder="Digite o texto...">${props.text || ''}</textarea>
            <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px;">
                <div>
                    <label style="font-size:.75rem;">Tamanho</label>
                    <input type="number" class="scene-text-size" min="8" max="300" value="${props.size || 48}" step="1">
                </div>
                <div>
                    <label style="font-size:.75rem;">Cor</label>
                    <input type="color" class="scene-text-color" value="${props.color || '#ffffff'}" style="width:100%; height:34px;">
                </div>
            </div>
            <div style="margin-top:6px;">
                <label style="font-size:.75rem;">Posição</label>
                <div class="position-grid text-pos-grid" style="max-width:180px;">
                    <button type="button" data-pos="superior esquerda" class="${props.position === 'superior esquerda' ? 'active' : ''}">↖</button>
                    <button type="button" data-pos="superior" class="${props.position === 'superior' ? 'active' : ''}">↑</button>
                    <button type="button" data-pos="superior direita" class="${props.position === 'superior direita' ? 'active' : ''}">↗</button>
                    <button type="button" data-pos="esquerda" class="${props.position === 'esquerda' ? 'active' : ''}">←</button>
                    <button type="button" data-pos="centro" class="${(!props.position || props.position === 'centro') ? 'active' : ''}">●</button>
                    <button type="button" data-pos="direita" class="${props.position === 'direita' ? 'active' : ''}">→</button>
                    <button type="button" data-pos="inferior esquerda" class="${props.position === 'inferior esquerda' ? 'active' : ''}">↙</button>
                    <button type="button" data-pos="inferior" class="${props.position === 'inferior' ? 'active' : ''}">↓</button>
                    <button type="button" data-pos="inferior direita" class="${props.position === 'inferior direita' ? 'active' : ''}">↘</button>
                </div>
            </div>
            <div style="margin-top:8px;">
                <label style="font-size:.75rem;">Efeito de Transição (Entrada)</label>
                <select class="scene-element-transition" style="width: 100%;">
                    <option value="none" ${props.transition === 'none' ? 'selected' : ''}>Seco</option>
                    <option value="fade" ${props.transition === 'fade' ? 'selected' : ''}>Esmaecer (Fade)</option>
                    <option value="slide_left" ${props.transition === 'slide_left' ? 'selected' : ''}>Deslizar da Esquerda</option>
                    <option value="slide_right" ${props.transition === 'slide_right' ? 'selected' : ''}>Deslizar da Direita</option>
                    <option value="slide_up" ${props.transition === 'slide_up' ? 'selected' : ''}>Deslizar de Baixo</option>
                    <option value="slide_down" ${props.transition === 'slide_down' ? 'selected' : ''}>Deslizar de Cima</option>
                </select>
            </div>

            <!-- Controle fino: posição X, Y em pixels -->
            <details class="text-fine-ctrl" style="margin-top:10px; border:1px solid rgba(255,255,255,.1); border-radius:10px; padding:8px 12px;">
                <summary style="cursor:pointer; font-weight:600; font-size:.85rem; user-select:none;">
                    🎯 Controle fino (pixels)
                </summary>
                <p class="hint" style="margin:6px 0 10px; font-size:.7rem; opacity:.7;">Baseado na resolução de saída. Deixe em branco para usar a posição rápida.</p>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;">
                    <div>
                        <label style="font-size:.7rem;">Posição X (px)</label>
                        <input type="number" class="text-px-x" step="1" placeholder="(centro)" value="${props.px_x !== undefined && props.px_x !== null ? props.px_x : ''}" style="padding:4px; font-size:.78rem; width:100%;">
                    </div>
                    <div>
                        <label style="font-size:.7rem;">Posição Y (px)</label>
                        <input type="number" class="text-px-y" step="1" placeholder="(centro)" value="${props.px_y !== undefined && props.px_y !== null ? props.px_y : ''}" style="padding:4px; font-size:.78rem; width:100%;">
                    </div>
                </div>
                <button type="button" class="vc-btn vc-btn-primary vc-btn-sm text-apply-btn" style="width:100%; font-size:.75rem; padding:4px;">
                    ▶ Aplicar ao preview
                </button>
            </details>
        `;

        const textarea = container.querySelector('.scene-text-input');
        const sizeInput = container.querySelector('.scene-text-size');
        const colorInput = container.querySelector('.scene-text-color');
        const textGrid = container.querySelector('.text-pos-grid');
        const transSelect = container.querySelector('.scene-element-transition');

        textarea.addEventListener('input', () => {
            props.text = textarea.value;
            refreshPreviewNow();
        });
        sizeInput.addEventListener('input', () => {
            props.size = parseInt(sizeInput.value) || 48;
            _syncFineFromQuickForTextElement(container, props);
            refreshPreviewNow();
        });
        colorInput.addEventListener('input', () => {
            props.color = colorInput.value;
            refreshPreviewNow();
        });
        textGrid.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', () => {
                textGrid.querySelectorAll('button').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                props.position = btn.dataset.pos;
                _syncFineFromQuickForTextElement(container, props);
                refreshPreviewNow();
            });
        });
        transSelect.addEventListener('change', () => {
            props.transition = transSelect.value;
        });

        // Controle fino listeners
        const pxXInput = container.querySelector('.text-px-x');
        const pxYInput = container.querySelector('.text-px-y');
        const applyBtn = container.querySelector('.text-apply-btn');

        const saveFineProps = () => {
            props.px_x = pxXInput.value.trim() !== '' ? parseInt(pxXInput.value) : null;
            props.px_y = pxYInput.value.trim() !== '' ? parseInt(pxYInput.value) : null;
        };

        [pxXInput, pxYInput].forEach(inp => {
            inp.addEventListener('change', saveFineProps);
            inp.addEventListener('input', saveFineProps);
        });

        applyBtn.addEventListener('click', () => {
            saveFineProps();
            refreshPreviewNow();
            showToast('Preview atualizado com controle fino!', 'success');
        });
    } else if (type === 'animation') {
        container.innerHTML = `
            <label style="font-size:.75rem;">Animação da Galeria</label>
            <select class="scene-anim-select">
                <option value="particulas" ${props.name === 'particulas' ? 'selected' : ''}>✨ Partículas</option>
                <option value="fumaca" ${props.name === 'fumaca' ? 'selected' : ''}>🌫️ Fumaça</option>
                <option value="brilho" ${props.name === 'brilho' ? 'selected' : ''}>💎 Brilho</option>
                <option value="fogo" ${props.name === 'fogo' ? 'selected' : ''}>🔥 Fogo</option>
                <option value="chuva" ${props.name === 'chuva' ? 'selected' : ''}>🌧️ Chuva</option>
                <option value="neve" ${props.name === 'neve' ? 'selected' : ''}>❄️ Neve</option>
                <option value="faiscas" ${props.name === 'faiscas' ? 'selected' : ''}>⚡ Faíscas</option>
                <option value="explosao" ${props.name === 'explosao' ? 'selected' : ''}>💥 Explosão</option>
                <option value="luz" ${props.name === 'luz' ? 'selected' : ''}>💡 Luz</option>
                <option value="loop_bg" ${props.name === 'loop_bg' ? 'selected' : ''}>🔄 Loop Background</option>
            </select>
            <div class="volume-control" style="margin-top:6px;">
                <label>🔥 Intensidade</label>
                <input type="range" min="10" max="100" value="${props.intensity || 50}" class="scene-anim-intensity">
                <span class="vol-value">${props.intensity || 50}%</span>
            </div>
        `;
        if (!props.name) props.name = 'particulas';
        if (!props.intensity) props.intensity = 50;

        const animSelect = container.querySelector('.scene-anim-select');
        const intensityRange = container.querySelector('.scene-anim-intensity');

        animSelect.addEventListener('change', () => {
            props.name = animSelect.value;
            refreshPreviewNow();
        });
        intensityRange.addEventListener('input', () => {
            intensityRange.nextElementSibling.textContent = intensityRange.value + '%';
            props.intensity = parseInt(intensityRange.value);
            refreshPreviewNow();
        });
    }
}

/**
 * Toggle do accordion interno de um elemento de cena (minimizar/expandir).
 */
function toggleSceneElement(header) {
    const el = header.closest('.scene-element');
    el.classList.toggle('collapsed');
}

/**
 * Toggle o card da cena (expandir/colapsar).
 */
function toggleSceneCard(header) {
    const card = header.closest('.scene-card');
    card.classList.toggle('collapsed');
}

/**
 * Remove uma cena.
 */
function removeScene(sceneId) {
    if (!confirm('Remover esta cena e todos os seus elementos?')) return;
    state.scenes = (state.scenes || []).filter(s => s.scene_id !== sceneId);
    const card = document.querySelector(`.scene-card[data-scene-id="${sceneId}"]`);
    if (card) {
        card.style.opacity = '0';
        card.style.transform = 'translateX(20px)';
        card.style.transition = 'all .3s';
        setTimeout(() => card.remove(), 300);
    }
    setTimeout(() => {
        renumberScenes();
        resolveAndRefreshTimeline();
    }, 350);
    showToast('Cena removida!', 'info');
}

/**
 * Duplica uma cena.
 */
function duplicateScene(sceneId) {
    const source = (state.scenes || []).find(s => s.scene_id === sceneId);
    if (!source) return;

    sceneCounter++;
    const newScene = duplicateSceneConfig(source, sceneCounter);
    const sourceIndex = state.scenes.indexOf(source);
    state.scenes.splice(sourceIndex + 1, 0, newScene);

    // Re-render all scenes
    _rerenderAllScenes();
    resolveAndRefreshTimeline();
    showToast(`Cena duplicada!`, 'success');
}

/**
 * Move uma cena para cima ou para baixo.
 */
function moveScene(sceneId, direction) {
    const idx = (state.scenes || []).findIndex(s => s.scene_id === sceneId);
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= state.scenes.length) return;

    const [scene] = state.scenes.splice(idx, 1);
    state.scenes.splice(newIdx, 0, scene);

    _rerenderAllScenes();
    resolveAndRefreshTimeline();
}

/**
 * Remove um elemento de uma cena.
 */
function removeSceneElement(btn) {
    const el = btn.closest('.scene-element');
    const elementId = el.dataset.elementId;
    const sceneCard = el.closest('.scene-card');
    const sceneId = sceneCard?.dataset.sceneId;

    // Remove do config
    const scene = (state.scenes || []).find(s => s.scene_id === sceneId);
    if (scene) {
        scene.elements = scene.elements.filter(e => e.id !== elementId);
    }

    el.remove();

    // Update badge
    if (scene && sceneCard) {
        const badge = sceneCard.querySelector('.scene-card-badge');
        const n = scene.elements.length;
        badge.textContent = `${n} elemento${n !== 1 ? 's' : ''}`;
    }

    resolveAndRefreshTimeline();
}

/**
 * Toggle do dropdown de adicionar elemento.
 */
function toggleAddElementDropdown(btn, sceneId) {
    // Remove existing dropdown and active classes
    document.querySelectorAll('.add-element-dropdown').forEach(d => d.remove());
    document.querySelectorAll('.scene-card').forEach(c => c.classList.remove('dropdown-active'));

    const card = btn.closest('.scene-card');
    if (card) card.classList.add('dropdown-active');

    const dropdown = document.createElement('div');
    dropdown.className = 'add-element-dropdown';
    dropdown.innerHTML = `
        <button type="button" onclick="addElementToScene('${sceneId}', 'background')">🖼️ Fundo</button>
        <button type="button" onclick="addElementToScene('${sceneId}', 'audio')">🎵 Áudio</button>
        <button type="button" onclick="addElementToScene('${sceneId}', 'overlay')">📸 Imagem Sobreposta</button>
        <button type="button" onclick="addElementToScene('${sceneId}', 'text')">📝 Texto</button>
        <button type="button" onclick="addElementToScene('${sceneId}', 'secondary_audio')">🎶 Áudio Secundário</button>
        <button type="button" onclick="addElementToScene('${sceneId}', 'custom_anim')">🎞️ GIF / Vídeo (Custom)</button>
    `;

    btn.parentElement.appendChild(dropdown);

    // Close on click outside
    setTimeout(() => {
        document.addEventListener('click', function handler(e) {
            if (!dropdown.contains(e.target) && e.target !== btn) {
                dropdown.remove();
                if (card) card.classList.remove('dropdown-active');
                document.removeEventListener('click', handler);
            }
        });
    }, 50);
}

/**
 * Adiciona um novo elemento a uma cena.
 */
function addElementToScene(sceneId, type) {
    const scene = (state.scenes || []).find(s => s.scene_id === sceneId);
    if (!scene) return;

    // Close dropdown and remove active classes
    document.querySelectorAll('.add-element-dropdown').forEach(d => d.remove());
    document.querySelectorAll('.scene-card').forEach(c => c.classList.remove('dropdown-active'));

    const labels = {
        background: 'Fundo', audio: 'Áudio', overlay: 'Imagem Sobreposta',
        text: 'Texto', secondary_audio: 'Áudio Secundário',
        animation: 'Animação Galeria', custom_anim: 'GIF / Vídeo Custom',
    };

    const existingOfType = scene.elements.filter(e => e.type === type).length;
    const suffix = `${type}_${existingOfType + 1}`;
    const id = `${sceneId}_${suffix}`;

    const newElement = {
        id,
        id_suffix: suffix,
        label: `${labels[type]} ${existingOfType + 1}`,
        type,
        scene_id: sceneId,
        trigger: { event: 'SCENE_START', offset: 0 },
        end_mode: type === 'audio' ? 'resource_duration' : 'scene_end',
        z_level: scene.elements.length,
        properties: {},
    };

    scene.elements.push(newElement);

    // Render element
    const elemList = document.querySelector(`.scene-elements-list[data-scene-id="${sceneId}"]`);
    if (elemList) {
        renderSceneElement(elemList, newElement, scene);
    }

    // Update badge
    const card = document.querySelector(`.scene-card[data-scene-id="${sceneId}"]`);
    if (card) {
        const badge = card.querySelector('.scene-card-badge');
        const n = scene.elements.length;
        badge.textContent = `${n} elemento${n !== 1 ? 's' : ''}`;
    }

    resolveAndRefreshTimeline();
}

/**
 * Callback quando o end mode muda.
 */
function onEndModeChange(select) {
    const el = select.closest('.scene-element');
    const elementId = el.dataset.elementId;
    const sceneCard = el.closest('.scene-card');
    const sceneId = sceneCard?.dataset.sceneId;
    const value = select.value;

    const scene = (state.scenes || []).find(s => s.scene_id === sceneId);
    const elementConfig = scene?.elements.find(e => e.id === elementId);
    if (!elementConfig) return;

    if (value === 'resource_duration' || value === 'scene_end') {
        elementConfig.end_mode = value;
    } else if (value === 'duration') {
        elementConfig.end_mode = { duration: 5.0 };
    } else if (value === 'event') {
        elementConfig.end_mode = { event: 'SCENE_END', offset: 0 };
    }

    _populateEndModeExtra(el, elementConfig, scene);
    resolveAndRefreshTimeline();
}

/**
 * Re-renderiza todas as cenas (após reordenar/duplicar).
 */
function _rerenderAllScenes() {
    const container = document.getElementById('scenesList');
    if (!container) return;
    container.innerHTML = '';
    (state.scenes || []).forEach((scene, i) => renderScene(scene, i));
}

/**
 * Renumera as cenas visualmente.
 */
function renumberScenes() {
    document.querySelectorAll('#scenesList .scene-card').forEach((card, i) => {
        const num = card.querySelector('.scene-card-num');
        if (num) num.textContent = i + 1;
    });
}

// ══════════════════════════════════════════
// Timeline Resolution & Visual
// ══════════════════════════════════════════

/**
 * Resolve toda a timeline e atualiza a visualização.
 */
function resolveAndRefreshTimeline() {
    if (!state.scenes || state.scenes.length === 0) {
        document.getElementById('timelineVisual').style.display = 'none';
        return;
    }

    const engine = new TimelineEngine();

    // Adicionar cenas
    for (const scene of state.scenes) {
        engine.addScene(scene);
    }

    // Informar durações dos áudios
    const durations = state.sceneResourceDurations || {};
    for (const [id, dur] of Object.entries(durations)) {
        engine.setResourceDuration(id, dur);
    }

    // Resolver
    const result = engine.resolve();

    // Mostrar warnings apenas no console para evitar spam de toasts
    if (result.warnings.length > 0) {
        result.warnings.forEach(w => console.warn(w));
    }

    // Salvar resultado
    state.resolvedTimeline = result;
    state.totalDurationScenes = result.totalDuration;

    // Atualizar selects de eventos em todos os elementos do DOM
    refreshAllEventSelects();

    // Atualizar timeline visual
    renderTimelineVisual(engine, result);

    // Atualizar slider de preview
    const slider = document.getElementById('previewTimeSlider');
    const totalLabel = document.getElementById('previewTotalDuration');
    if (slider && state.useEventTimeline) {
        if (result.totalDuration > 0) {
            slider.disabled = false;
            slider.max = result.totalDuration.toFixed(1);
            totalLabel.textContent = `${result.totalDuration.toFixed(1)}s total`;
        } else {
            slider.disabled = true;
            slider.max = 0;
            totalLabel.textContent = '0.0s total';
        }
    }

    // Atualizar o canvas de preview na hora
    refreshPreviewNow();
}

/**
 * Atualiza dinamicamente as opções em todos os selects de evento do DOM (Modo Cenas).
 */
function refreshAllEventSelects() {
    if (!state.useEventTimeline) return;
    const engine = new TimelineEngine();
    engine.scenes = state.scenes || [];
    
    document.querySelectorAll('#scenesList .scene-element').forEach(el => {
        const sceneCard = el.closest('.scene-card');
        if (!sceneCard) return;
        const sceneId = sceneCard.dataset.sceneId;
        const elementId = el.dataset.elementId;
        const scene = state.scenes.find(s => s.scene_id === sceneId);
        if (!scene) return;
        const elementConfig = scene.elements.find(e => e.id === elementId);
        if (!elementConfig) return;

        const availableEvents = engine.getAvailableEvents(sceneId, elementId);

        // 1. Atualizar o select de Trigger Event (Evento de Início)
        const triggerSelect = el.querySelector('.trigger-event');
        if (triggerSelect) {
            const currentVal = triggerSelect.value || elementConfig.trigger?.event;
            triggerSelect.innerHTML = availableEvents.map(e =>
                `<option value="${e.value}"${currentVal === e.value ? ' selected' : ''}>${e.label}</option>`
            ).join('');
            if (elementConfig.trigger) {
                elementConfig.trigger.event = triggerSelect.value;
            }
        }

        // 2. Atualizar o select de End Event (Modo de fim até evento) se ativo
        const endEventSelect = el.querySelector('.end-event-select');
        if (endEventSelect) {
            const currentVal = endEventSelect.value || (typeof elementConfig.end_mode === 'object' ? elementConfig.end_mode.event : '');
            endEventSelect.innerHTML = availableEvents.map(e =>
                `<option value="${e.value}"${currentVal === e.value ? ' selected' : ''}>${e.label}</option>`
            ).join('');
            if (typeof elementConfig.end_mode === 'object' && elementConfig.end_mode.event) {
                elementConfig.end_mode.event = endEventSelect.value;
            }
        }
    });
}

/**
 * Renderiza a barra visual da timeline.
 */
function renderTimelineVisual(engine, result) {
    const container = document.getElementById('timelineVisual');
    const tracksEl = document.getElementById('timelineTracks');
    const rulerEl = document.getElementById('timelineRuler');
    const durationEl = document.getElementById('tlTotalDuration');

    if (!container || !tracksEl) return;

    const totalDuration = result.totalDuration;
    if (totalDuration <= 0) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';
    durationEl.textContent = `${totalDuration.toFixed(1)}s`;

    // Build timeline items
    const timeline = engine.getResolvedTimeline();

    // Group by type for tracks
    const typeOrder = ['background', 'audio', 'overlay', 'text', 'secondary_audio'];
    const typeLabels = {
        background: '🖼️ Fundo',
        audio: '🎵 Áudio',
        overlay: '📸 Overlay',
        text: '📝 Texto',
        secondary_audio: '🎶 Sec.Audio',
    };

    const tracksByType = {};
    for (const item of timeline) {
        if (!tracksByType[item.type]) tracksByType[item.type] = [];
        tracksByType[item.type].push(item);
    }

    // Scene separators (background color bands)
    let sceneColors = ['rgba(124,77,255,.08)', 'rgba(224,64,251,.06)'];

    let tracksHTML = '';
    for (const type of typeOrder) {
        const items = tracksByType[type];
        if (!items || items.length === 0) continue;

        let blocksHTML = '';
        for (const item of items) {
            const left = (item.start / totalDuration * 100).toFixed(2);
            const width = Math.max(0.5, ((item.end - item.start) / totalDuration * 100)).toFixed(2);
            const typeClass = type === 'background' ? 'bg' : type;
            const label = item.label || item.id.split('_').slice(-2).join(' ');
            blocksHTML += `<div class="timeline-block ${typeClass}" style="left:${left}%; width:${width}%;" title="${item.id}\n${item.start.toFixed(1)}s → ${item.end.toFixed(1)}s\nZ: ${item.z_level}">${label}</div>`;
        }

        tracksHTML += `
            <div class="timeline-track">
                <div class="timeline-track-label">${typeLabels[type] || type}</div>
                <div class="timeline-track-bar">${blocksHTML}</div>
            </div>
        `;
    }

    // Scene boundaries
    let sceneMarkersHTML = '';
    for (const scene of state.scenes) {
        const start = result.sceneStarts.get(scene.scene_id) || 0;
        const end = result.sceneEnds.get(scene.scene_id) || 0;
        if (start > 0) {
            const left = (start / totalDuration * 100).toFixed(2);
            sceneMarkersHTML += `<div style="position:absolute; top:0; bottom:0; left:${left}%; width:1px; background:rgba(124,77,255,.3); z-index:5;" title="${scene.name} start"></div>`;
        }
    }

    tracksEl.innerHTML = sceneMarkersHTML + tracksHTML;

    // Time ruler
    const steps = Math.min(10, Math.ceil(totalDuration));
    const stepSize = totalDuration / steps;
    let rulerHTML = '';
    for (let i = 0; i <= steps; i++) {
        rulerHTML += `<span>${(i * stepSize).toFixed(1)}s</span>`;
    }
    rulerEl.innerHTML = rulerHTML;
}

// ══════════════════════════════════════════
// Scene Mode: Submit — resolve tempos e monta formData
// ══════════════════════════════════════════

/**
 * Coleta dados das cenas para submissão (resolve tempos e monta como modo clássico).
 */
function collectScenesForSubmit() {
    if (!state.scenes || state.scenes.length === 0) return null;

    // Ensure resolved
    resolveAndRefreshTimeline();
    const result = state.resolvedTimeline;
    if (!result) return null;

    const audioItems = [];
    const bgSegments = [];
    const overlaySegments = [];
    const textOverlays = [];
    const secAudios = [];
    const customAnims = [];

    let audioIdx = 0, bgIdx = 0, ovIdx = 0, txtIdx = 0, saIdx = 0, caIdx = 0;

    for (const scene of state.scenes) {
        for (const el of scene.elements) {
            const r = result.resolved.get(el.id);
            if (!r) continue;

            const start = r.start || 0;
            const end = r.end || 0;

            if (el.type === 'background') {
                bgSegments.push({
                    index: bgIdx++,
                    start_sec: start,
                    end_sec: end,
                    element_id: el.id,
                    z_level: el.z_level || 0,
                    transition: el.properties?.transition || 'none',
                });
            } else if (el.type === 'audio') {
                audioItems.push({
                    index: audioIdx++,
                    type: 'upload',
                    volume: 100,
                    element_id: el.id,
                });
            } else if (el.type === 'overlay') {
                const props = el.properties || {};
                overlaySegments.push({
                    index: ovIdx++,
                    start_sec: start,
                    end_sec: end,
                    position: props.position || 'centro',
                    scale: props.scale || 50,
                    element_id: el.id,
                    z_level: el.z_level || 0,
                    transition: props.transition || 'none',
                    px_width: props.px_width !== undefined ? props.px_width : null,
                    px_height: props.px_height !== undefined ? props.px_height : null,
                    px_x: props.px_x !== undefined ? props.px_x : null,
                    px_y: props.px_y !== undefined ? props.px_y : null,
                });
            } else if (el.type === 'custom_anim') {
                const props = el.properties || {};
                customAnims.push({
                    index: caIdx++,
                    start_sec: start,
                    end_sec: end,
                    position: props.position || 'centro',
                    scale: props.scale || 30,
                    loop: props.loop !== false,
                    element_id: el.id,
                    z_level: el.z_level || 0,
                    transition: props.transition || 'none',
                    px_width: props.px_width !== undefined ? props.px_width : null,
                    px_height: props.px_height !== undefined ? props.px_height : null,
                    px_x: props.px_x !== undefined ? props.px_x : null,
                    px_y: props.px_y !== undefined ? props.px_y : null,
                });
            } else if (el.type === 'text') {
                const props = el.properties || {};
                textOverlays.push({
                    index: txtIdx++,
                    text: props.text || '',
                    font: '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
                    size: props.size || 48,
                    color: props.color || '#ffffff',
                    start_sec: start,
                    end_sec: end,
                    position: props.position || 'centro',
                    z_level: el.z_level || 0,
                    transition: props.transition || 'none',
                    px_x: props.px_x !== undefined ? props.px_x : null,
                    px_y: props.px_y !== undefined ? props.px_y : null,
                });
            } else if (el.type === 'secondary_audio') {
                const props = el.properties || {};
                secAudios.push({
                    index: saIdx++,
                    volume: props.volume || 20,
                    start_sec: start,
                    end_sec: end,
                    loop: props.loop !== false,
                    element_id: el.id,
                    z_level: el.z_level || 0,
                });
            }
        }
    }

    return { audioItems, bgSegments, overlaySegments, textOverlays, secAudios, customAnims };
}

// ══════════════════════════════════════════
// Templates: Scene Mode Support
// ══════════════════════════════════════════

/**
 * Override collectTemplateData para incluir cenas quando em modo cenas.
 */
const _originalCollectTemplateData = typeof collectTemplateData === 'function' ? collectTemplateData : null;

function collectTemplateDataWithScenes() {
    if (state.useEventTimeline && state.scenes && state.scenes.length > 0) {
        // Salvar no formato de cenas
        return {
            mode: 'scenes',
            resolution: state.resolution,
            scenes: state.scenes.map(s => ({
                scene_id: s.scene_id,
                name: s.name,
                description: s.description,
                preset_key: s.preset_key,
                elements: s.elements.map(el => ({
                    id: el.id,
                    id_suffix: el.id_suffix,
                    label: el.label,
                    type: el.type,
                    trigger: el.trigger,
                    end_mode: el.end_mode,
                    z_level: el.z_level,
                    properties: el.properties,
                })),
            })),
        };
    }
    // Fallback para modo clássico
    return collectTemplateData();
}

/**
 * Override applyTemplateData para suportar cenas.
 */
const _originalApplyTemplateData = typeof applyTemplateData === 'function' ? applyTemplateData : null;

function applyTemplateDataWithScenes(td) {
    if (td.mode === 'scenes' && td.scenes) {
        // Mudar para modo cenas
        const scenesChip = document.querySelector('.mode-chip[data-mode="scenes"]');
        if (scenesChip) switchEditorMode(scenesChip, 'scenes');

        // Limpar cenas existentes
        state.scenes = [];
        state.sceneResourceDurations = {};
        const container = document.getElementById('scenesList');
        if (container) container.innerHTML = '';

        // Resolução
        if (td.resolution) {
            state.resolution = td.resolution;
            document.getElementById('resolution').value = td.resolution;
            document.querySelectorAll('.res-chip').forEach(c => {
                c.classList.toggle('active', c.dataset.res === td.resolution);
            });
        }

        // Recriar cenas
        sceneCounter = 0;
        for (const sceneData of td.scenes) {
            sceneCounter++;
            state.scenes.push(sceneData);
            renderScene(sceneData, state.scenes.length - 1);
        }

        resolveAndRefreshTimeline();
        return;
    }

    // Fallback para modo clássico
    const classicChip = document.querySelector('.mode-chip[data-mode="classic"]');
    if (classicChip) switchEditorMode(classicChip, 'classic');
    applyTemplateData(td);
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

    // Modo cenas presets inicialização
    renderPresetSelector();

    updateLayers();
    refreshTimelineUI();

    // Fechar modais com Escape
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSaveTemplateModal();
            closeLoadTemplateModal();
        }
    });
});

// Sincronização automática para imagem/gif em Modo Cenas
function _syncFineFromQuickForSceneElement(container, props) {
    const scaleRange = container.querySelector('.overlay-scale-range');
    const activePos  = container.querySelector('.overlay-pos-grid button.active');
    if (!scaleRange || !activePos) return;

    const scale  = parseInt(scaleRange.value);
    const posKey = activePos.dataset.pos || 'centro';
    const { w, h } = _scaleToPx(container, scale);
    const { x, y } = _posToPx(posKey, w, h || 0);

    const pxW = container.querySelector('.overlay-px-w');
    const pxH = container.querySelector('.overlay-px-h');
    const pxX = container.querySelector('.overlay-px-x');
    const pxY = container.querySelector('.overlay-px-y');

    if (pxW) pxW.value = w;
    if (pxH && h !== null) pxH.value = h;
    if (pxX) pxX.value = x;
    if (pxY) pxY.value = y;

    // Salvar nas propriedades
    props.px_width = w;
    props.px_height = h;
    props.px_x = x;
    props.px_y = y;
}

// Sincronização automática para textos em Modo Cenas
function _syncFineFromQuickForTextElement(container, props) {
    const sizeInput = container.querySelector('.scene-text-size');
    const activePos  = container.querySelector('.text-pos-grid button.active');
    if (!sizeInput || !activePos) return;

    const size = parseInt(sizeInput.value) || 48;
    const posKey = activePos.dataset.pos || 'centro';
    const { x, y } = _posToPx(posKey, 0, 0); // Texto estima no centro

    const pxX = container.querySelector('.text-px-x');
    const pxY = container.querySelector('.text-px-y');

    if (pxX) pxX.value = x;
    if (pxY) pxY.value = y;

    // Salvar nas propriedades
    props.px_x = x;
    props.px_y = y;
}

// Intercepta enter no label editável do elemento de cena
function handleLabelKeydown(e) {
    if (e.key === 'Enter') {
        e.preventDefault();
        e.target.blur();
    }
}

// Salva o nome personalizado do elemento no estado
function updateElementLabel(elSpan) {
    const sceneEl = elSpan.closest('.scene-element');
    const sceneCard = elSpan.closest('.scene-card');
    if (!sceneEl || !sceneCard) return;

    const sceneId = sceneCard.dataset.sceneId;
    const elementId = sceneEl.dataset.elementId;

    const scene = state.scenes.find(s => s.scene_id === sceneId);
    if (!scene) return;

    const element = scene.elements.find(e => e.id === elementId);
    if (!element) return;

    const newLabel = elSpan.textContent.trim();
    if (newLabel) {
        element.label = newLabel;
        resolveAndRefreshTimeline();
    } else {
        // Fallback para o label original do tipo se apagado
        const typeLabels = {
            background: '🖼️ Fundo',
            audio: '🎵 Áudio',
            overlay: '📸 Overlay',
            text: '📝 Texto',
            secondary_audio: '🎶 Sec.Audio',
            custom_anim: '🎞️ Anim.Custom',
        };
        elSpan.textContent = typeLabels[element.type] || element.type;
        element.label = elSpan.textContent;
        resolveAndRefreshTimeline();
    }
}

