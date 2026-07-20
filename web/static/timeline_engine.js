/**
 * TimelineEngine — Motor de resolução de timeline baseada em eventos.
 *
 * Cada elemento tem:
 *   - trigger: { event: string, offset: number }   → quando começa
 *   - end_mode: "resource_duration" | "scene_end" | { duration: N } | { event: string, offset: N }
 *   - z_level: number → nível de renderização (maior = mais à frente)
 *
 * Eventos reconhecidos:
 *   SCENE_START, SCENE_END,
 *   AUDIO_START:<id>, AUDIO_END:<id>,
 *   ELEMENT_START:<id>, ELEMENT_END:<id>,
 *   ABSOLUTE
 *
 * O engine resolve todas as dependências e gera uma timeline com tempos absolutos.
 */

class TimelineEngine {
    constructor() {
        /** @type {Array<SceneConfig>} */
        this.scenes = [];
        /** @type {Map<string, number>} elementId → duration (seconds) */
        this.resourceDurations = new Map();
        /** @type {Map<string, {start: number, end: number}>} elementId → resolved times */
        this.resolved = new Map();
        /** @type {Map<string, number>} sceneId → resolved start */
        this.sceneStarts = new Map();
        /** @type {Map<string, number>} sceneId → resolved end */
        this.sceneEnds = new Map();
        /** @type {Array<string>} warnings */
        this.warnings = [];
    }

    // ── Configuração ──

    /**
     * Limpa tudo.
     */
    reset() {
        this.scenes = [];
        this.resourceDurations.clear();
        this.resolved.clear();
        this.sceneStarts.clear();
        this.sceneEnds.clear();
        this.warnings = [];
    }

    /**
     * Adiciona uma cena.
     * @param {SceneConfig} scene
     */
    addScene(scene) {
        this.scenes.push(scene);
    }

    /**
     * Informa a duração de um recurso (áudio, vídeo).
     * @param {string} elementId
     * @param {number} durationSec
     */
    setResourceDuration(elementId, durationSec) {
        this.resourceDurations.set(elementId, durationSec);
    }

    // ── Resolução ──

    /**
     * Resolve toda a timeline, retornando tempos absolutos.
     * @returns {{ resolved: Map, sceneStarts: Map, sceneEnds: Map, totalDuration: number, warnings: string[] }}
     */
    resolve() {
        this.resolved.clear();
        this.sceneStarts.clear();
        this.sceneEnds.clear();
        this.warnings = [];

        let cumulativeTime = 0;

        for (const scene of this.scenes) {
            const sceneStart = cumulativeTime;
            this.sceneStarts.set(scene.scene_id, sceneStart);

            // Resolve elementos nesta cena
            const elementIds = scene.elements.map(e => e.id);
            const resolved = this._resolveSceneElements(scene, sceneStart);

            // O fim da cena = máximo end de todos os elementos
            let sceneEnd = sceneStart;
            for (const el of scene.elements) {
                const r = resolved.get(el.id);
                if (r && r.end > sceneEnd) {
                    sceneEnd = r.end;
                }
            }

            this.sceneEnds.set(scene.scene_id, sceneEnd);

            // Salvar resolved de cada elemento
            for (const [id, times] of resolved) {
                this.resolved.set(id, times);
            }

            cumulativeTime = sceneEnd;
        }

        return {
            resolved: new Map(this.resolved),
            sceneStarts: new Map(this.sceneStarts),
            sceneEnds: new Map(this.sceneEnds),
            totalDuration: cumulativeTime,
            warnings: [...this.warnings],
        };
    }

    /**
     * Resolve elementos dentro de uma cena.
     * Usa iteração até convergir (max 20 passes) para resolver dependências.
     */
    _resolveSceneElements(scene, sceneStart) {
        const resolved = new Map();
        const elements = scene.elements;

        // Inicializar com valores desconhecidos
        for (const el of elements) {
            resolved.set(el.id, { start: null, end: null });
        }

        const MAX_PASSES = 20;
        for (let pass = 0; pass < MAX_PASSES; pass++) {
            let changed = false;

            for (const el of elements) {
                const prev = resolved.get(el.id);
                const newStart = this._resolveEventTime(el.trigger, scene.scene_id, sceneStart, resolved);
                const newEnd = this._resolveEndTime(el, scene.scene_id, sceneStart, newStart, resolved);

                if (newStart !== prev.start || newEnd !== prev.end) {
                    resolved.set(el.id, { start: newStart, end: newEnd });
                    changed = true;
                }
            }

            if (!changed) break;

            if (pass === MAX_PASSES - 1) {
                this.warnings.push(
                    `⚠️ Cena "${scene.name || scene.scene_id}": possível dependência circular. Alguns tempos podem estar incorretos.`
                );
            }
        }

        return resolved;
    }

    /**
     * Resolve o tempo absoluto de um evento trigger.
     */
    _resolveEventTime(trigger, currentSceneId, sceneStart, localResolved) {
        if (!trigger) return sceneStart;

        const event = trigger.event || 'SCENE_START';
        const offset = trigger.offset || 0;

        // Evento absoluto
        if (event === 'ABSOLUTE') {
            return offset;
        }

        // Início da cena
        if (event === 'SCENE_START') {
            return sceneStart + offset;
        }

        // Fim da cena (da cena atual — pode ser desconhecido ainda)
        if (event === 'SCENE_END') {
            const sceneEnd = this.sceneEnds.get(currentSceneId);
            if (sceneEnd !== undefined) return sceneEnd + offset;
            // Fallback: usar o max end dos elementos já resolvidos
            let maxEnd = sceneStart;
            for (const [, r] of localResolved) {
                if (r.end !== null && r.end > maxEnd) maxEnd = r.end;
            }
            return maxEnd + offset;
        }

        // AUDIO_START:<id> ou AUDIO_END:<id>
        if (event.startsWith('AUDIO_START:') || event.startsWith('ELEMENT_START:')) {
            const refId = event.split(':').slice(1).join(':');
            const r = localResolved.get(refId) || this.resolved.get(refId);
            if (r && r.start !== null) return r.start + offset;
            return null; // Não resolvido ainda
        }

        if (event.startsWith('AUDIO_END:') || event.startsWith('ELEMENT_END:')) {
            const refId = event.split(':').slice(1).join(':');
            const r = localResolved.get(refId) || this.resolved.get(refId);
            if (r && r.end !== null) return r.end + offset;
            return null; // Não resolvido ainda
        }

        this.warnings.push(`Evento desconhecido: "${event}"`);
        return sceneStart + offset;
    }

    /**
     * Resolve o tempo de fim de um elemento.
     */
    _resolveEndTime(element, currentSceneId, sceneStart, startTime, localResolved) {
        if (startTime === null) return null;

        const endMode = element.end_mode;

        // Duração do recurso (áudio/vídeo)
        if (endMode === 'resource_duration') {
            const dur = this.resourceDurations.get(element.id);
            if (dur !== undefined && dur !== null) {
                return startTime + dur;
            }
            // Duração desconhecida — usar placeholder
            this.warnings.push(
                `⏳ "${element.id}": duração do recurso desconhecida. Carregue o áudio/vídeo.`
            );
            return startTime + 5; // placeholder 5s
        }

        // Fim da cena
        if (endMode === 'scene_end') {
            // Será atualizado no final quando sceneEnd for calculado
            // Por enquanto, retornar o máximo conhecido
            let maxEnd = startTime + 1;
            for (const [id, r] of localResolved) {
                if (id !== element.id && r.end !== null && r.end > maxEnd) {
                    maxEnd = r.end;
                }
            }
            return maxEnd;
        }

        // Duração fixa
        if (typeof endMode === 'object' && endMode.duration !== undefined) {
            return startTime + endMode.duration;
        }

        // Evento
        if (typeof endMode === 'object' && endMode.event) {
            const endTime = this._resolveEventTime(endMode, currentSceneId, sceneStart, localResolved);
            if (endTime !== null) return endTime;
            return null;
        }

        // Fallback
        return startTime + 5;
    }

    // ── Utilitários ──

    /**
     * Retorna a timeline resolvida como array plano.
     * @returns {Array<{id, scene_id, type, start, end, z_level, properties}>}
     */
    getResolvedTimeline() {
        const result = [];
        for (const scene of this.scenes) {
            for (const el of scene.elements) {
                const r = this.resolved.get(el.id);
                result.push({
                    id: el.id,
                    label: el.label || el.id,
                    scene_id: scene.scene_id,
                    type: el.type,
                    start: r ? r.start : 0,
                    end: r ? r.end : 0,
                    z_level: el.z_level || 0,
                    properties: el.properties || {},
                });
            }
        }
        // Ordenar por z_level
        result.sort((a, b) => a.z_level - b.z_level);
        return result;
    }

    /**
     * Retorna duração total.
     */
    getTotalDuration() {
        let max = 0;
        for (const [, end] of this.sceneEnds) {
            if (end > max) max = end;
        }
        return max;
    }

    /**
     * Retorna os eventos disponíveis para um elemento em uma cena.
     * Usado para popular os dropdowns de seleção de evento.
     * @param {string} sceneId
     * @param {string} excludeElementId — não incluir o próprio elemento
     * @returns {Array<{value, label}>}
     */
    getAvailableEvents(sceneId, excludeElementId) {
        const events = [
            { value: 'SCENE_START', label: '🎬 Início da Cena' },
            { value: 'SCENE_END', label: '🏁 Fim da Cena' },
            { value: 'ABSOLUTE', label: '⏱️ Tempo Absoluto' },
        ];

        const scene = this.scenes.find(s => s.scene_id === sceneId);
        if (scene) {
            for (const el of scene.elements) {
                if (el.id === excludeElementId) continue;
                if (!el.export_events) continue; // Só exporta se explicitamente ativado!

                const label = el.label || el.id;
                events.push(
                    { value: `ELEMENT_START:${el.id}`, label: `▶️ Início de "${label}"` },
                    { value: `ELEMENT_END:${el.id}`, label: `⏹️ Fim de "${label}"` },
                );
                // Mapeia inícios e fins genéricos de elementos de cena
            }
        }

        return events;
    }

    /**
     * Retorna os modos de fim disponíveis.
     * @returns {Array<{value, label}>}
     */
    getAvailableEndModes() {
        return [
            { value: 'resource_duration', label: '📏 Duração do Recurso (áudio/vídeo)' },
            { value: 'scene_end', label: '🏁 Até o Fim da Cena' },
            { value: 'duration', label: '⏱️ Duração Fixa (segundos)' },
            { value: 'event', label: '🔗 Até um Evento' },
        ];
    }
}

// ══════════════════════════════════════════
// Presets de Cena
// ══════════════════════════════════════════

const SCENE_PRESETS = {
    quiz_question: {
        name: '❓ Pergunta de Quiz',
        description: 'Fundo + narração da pergunta + timer + resposta',
        elements: [
            {
                id_suffix: 'bg',
                label: 'Fundo',
                type: 'background',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 0,
            },
            {
                id_suffix: 'narration',
                label: 'Narração da Pergunta',
                type: 'audio',
                trigger: { event: 'SCENE_START', offset: 0.5 },
                end_mode: 'resource_duration',
                z_level: 1,
                export_events: true,
            },
            {
                id_suffix: 'question_text',
                label: 'Texto da Pergunta',
                type: 'text',
                trigger: { event: 'SCENE_START', offset: 0.3 },
                end_mode: 'scene_end',
                z_level: 5,
                properties: { position: 'superior', size: 48, color: '#ffffff' },
            },
            {
                id_suffix: 'timer',
                label: 'Timer / Contagem',
                type: 'overlay',
                trigger: { event: 'AUDIO_END:{{narration}}', offset: 0.5 },
                end_mode: { duration: 10.0 },
                z_level: 8,
                export_events: true,
            },
            {
                id_suffix: 'answer_narration',
                label: 'Narração da Resposta',
                type: 'audio',
                trigger: { event: 'ELEMENT_END:{{timer}}', offset: 0.5 },
                end_mode: 'resource_duration',
                z_level: 2,
                export_events: true,
            },
            {
                id_suffix: 'answer_text',
                label: 'Texto da Resposta',
                type: 'text',
                trigger: { event: 'ELEMENT_START:{{answer_narration}}', offset: 0 },
                end_mode: 'scene_end',
                z_level: 6,
                properties: { position: 'inferior', size: 42, color: '#00ff88' },
            },
        ],
    },

    intro: {
        name: '🎬 Intro / Abertura',
        description: 'Fundo + logo + narração de abertura + efeito sonoro',
        elements: [
            {
                id_suffix: 'bg',
                label: 'Fundo',
                type: 'background',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 0,
            },
            {
                id_suffix: 'logo',
                label: 'Logo / Marca',
                type: 'overlay',
                trigger: { event: 'SCENE_START', offset: 0.3 },
                end_mode: 'scene_end',
                z_level: 5,
                properties: { position: 'superior', scale: 30 },
            },
            {
                id_suffix: 'narration',
                label: 'Narração de Abertura',
                type: 'audio',
                trigger: { event: 'SCENE_START', offset: 1.0 },
                end_mode: 'resource_duration',
                z_level: 1,
                export_events: true,
            },
            {
                id_suffix: 'title_text',
                label: 'Título',
                type: 'text',
                trigger: { event: 'SCENE_START', offset: 0.5 },
                end_mode: 'scene_end',
                z_level: 6,
                properties: { position: 'centro', size: 64, color: '#ffffff' },
            },
            {
                id_suffix: 'sfx',
                label: 'Efeito Sonoro (música de fundo)',
                type: 'secondary_audio',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 0,
                properties: { volume: 20, loop: true },
            },
        ],
    },

    answer_reveal: {
        name: '🎯 Revelação de Resposta',
        description: 'Fundo + narração da resposta + destaque visual',
        elements: [
            {
                id_suffix: 'bg',
                label: 'Fundo',
                type: 'background',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 0,
            },
            {
                id_suffix: 'narration',
                label: 'Narração da Resposta',
                type: 'audio',
                trigger: { event: 'SCENE_START', offset: 0.5 },
                end_mode: 'resource_duration',
                z_level: 1,
                export_events: true,
            },
            {
                id_suffix: 'answer_text',
                label: 'Texto da Resposta',
                type: 'text',
                trigger: { event: 'SCENE_START', offset: 0.3 },
                end_mode: 'scene_end',
                z_level: 6,
                properties: { position: 'centro', size: 56, color: '#00ff88' },
            },
            {
                id_suffix: 'highlight',
                label: 'Destaque Visual',
                type: 'overlay',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 3,
                properties: { position: 'centro', scale: 80 },
            },
        ],
    },

    simple: {
        name: '📄 Cena Simples',
        description: 'Apenas fundo + narração',
        elements: [
            {
                id_suffix: 'bg',
                label: 'Fundo',
                type: 'background',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'scene_end',
                z_level: 0,
            },
            {
                id_suffix: 'narration',
                label: 'Narração',
                type: 'audio',
                trigger: { event: 'SCENE_START', offset: 0 },
                end_mode: 'resource_duration',
                z_level: 1,
                export_events: true,
            },
        ],
    },

    empty: {
        name: '🆕 Cena Vazia',
        description: 'Sem elementos — monte do zero',
        elements: [],
    },
};

/**
 * Instancia uma cena a partir de um preset.
 * Gera IDs únicos substituindo {{ref}} por IDs reais.
 * @param {string} presetKey — chave de SCENE_PRESETS
 * @param {number} sceneIndex — número sequencial da cena
 * @returns {SceneConfig}
 */
function instantiatePreset(presetKey, sceneIndex) {
    const preset = SCENE_PRESETS[presetKey];
    if (!preset) throw new Error(`Preset "${presetKey}" não encontrado.`);

    const sceneId = `scene_${sceneIndex}_${Date.now().toString(36)}`;
    const idMap = {};

    // Gerar IDs reais
    const elements = preset.elements.map(tpl => {
        const id = `${sceneId}_${tpl.id_suffix}`;
        idMap[tpl.id_suffix] = id;
        return { ...tpl, id, scene_id: sceneId };
    });

    // Substituir referências {{xxx}} nos triggers e end_modes
    for (const el of elements) {
        el.trigger = _replaceRefs(el.trigger, idMap);
        el.end_mode = _replaceRefs(el.end_mode, idMap);
    }

    return {
        scene_id: sceneId,
        name: `${preset.name} #${sceneIndex}`,
        description: preset.description,
        preset_key: presetKey,
        elements,
    };
}

/**
 * Substitui referências {{xxx}} em triggers/end_modes.
 */
function _replaceRefs(obj, idMap) {
    if (typeof obj === 'string') {
        return obj.replace(/\{\{(\w+)\}\}/g, (_, key) => idMap[key] || key);
    }
    if (obj && typeof obj === 'object') {
        const result = {};
        for (const [k, v] of Object.entries(obj)) {
            result[k] = _replaceRefs(v, idMap);
        }
        return result;
    }
    return obj;
}

/**
 * Duplica uma cena, gerando novos IDs únicos.
 * @param {SceneConfig} sourceScene
 * @param {number} newIndex
 * @returns {SceneConfig}
 */
function duplicateSceneConfig(sourceScene, newIndex) {
    const newSceneId = `scene_${newIndex}_${Date.now().toString(36)}`;
    const idMap = {};

    // Mapear IDs antigos → novos
    for (const el of sourceScene.elements) {
        const suffix = el.id.split('_').slice(-1)[0] || el.id;
        const oldId = el.id;
        const newId = `${newSceneId}_${el.id_suffix || suffix}`;
        idMap[oldId] = newId;
    }

    const elements = sourceScene.elements.map(el => {
        const newId = idMap[el.id] || `${newSceneId}_${el.id_suffix || el.id}`;
        const newEl = {
            ...el,
            id: newId,
            scene_id: newSceneId,
            trigger: _replaceOldIds(el.trigger, idMap),
            end_mode: _replaceOldIds(el.end_mode, idMap),
        };
        return newEl;
    });

    return {
        scene_id: newSceneId,
        name: sourceScene.name.replace(/#\d+/, `#${newIndex}`),
        description: sourceScene.description,
        preset_key: sourceScene.preset_key,
        elements,
    };
}

/**
 * Substitui IDs antigos por novos em triggers/end_modes.
 */
function _replaceOldIds(obj, idMap) {
    if (typeof obj === 'string') {
        for (const [oldId, newId] of Object.entries(idMap)) {
            obj = obj.replace(oldId, newId);
        }
        return obj;
    }
    if (obj && typeof obj === 'object') {
        const result = {};
        for (const [k, v] of Object.entries(obj)) {
            result[k] = _replaceOldIds(v, idMap);
        }
        return result;
    }
    return obj;
}
