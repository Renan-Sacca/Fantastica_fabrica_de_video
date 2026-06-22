/**
 * Dashboard JS — Fantástica Fábrica de Vídeo v2
 * Comunica com o backend via multipart/form-data + SSE
 */

// ── Tabs ──
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabId = tab.dataset.tab;
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        tab.classList.add('active');
        document.getElementById(`tab-${tabId}`).classList.add('active');
    });
});

// ── Range Sliders ──
['speed', 'reading_speed', 'scroll_speed'].forEach(name => {
    const input = document.getElementById(name);
    const valueEl = document.getElementById(`${name}-value`);
    if (input && valueEl) {
        input.addEventListener('input', () => {
            valueEl.textContent = parseFloat(input.value).toFixed(1) + 'x';
            estimateDuration(); // atualiza estimativa ao mudar velocidade
        });
    }
});

// ── File Preview: Foto de Perfil ──
const photoInput = document.getElementById('contact_photo');
if (photoInput) {
    photoInput.addEventListener('change', () => {
        const file = photoInput.files[0];
        if (!file) return;
        const preview = document.getElementById('photo-preview');
        const reader = new FileReader();
        reader.onload = e => {
            preview.innerHTML = `<img src="${e.target.result}" alt="Foto">`;
        };
        reader.readAsDataURL(file);
    });
}

// ── File Preview: Papel de Parede ──
const wallpaperInput = document.getElementById('wallpaper');
if (wallpaperInput) {
    wallpaperInput.addEventListener('change', () => {
        const file = wallpaperInput.files[0];
        const bgColorGroup = document.getElementById('bg-color-group');
        if (!file) {
            if (bgColorGroup) bgColorGroup.style.display = 'block';
            return;
        }
        // Esconde o color picker quando há wallpaper
        if (bgColorGroup) bgColorGroup.style.display = 'none';
        const preview = document.getElementById('wallpaper-preview');
        const reader = new FileReader();
        reader.onload = e => {
            preview.innerHTML = `<img src="${e.target.result}" alt="Papel de parede">`;
        };
        reader.readAsDataURL(file);
    });
}

// ── Color picker de fundo ──
(function () {
    const presets = document.querySelectorAll('.bg-color-btn');
    const hiddenInput = document.getElementById('bg_color');
    const customInput = document.getElementById('bg-color-custom');

    function selectColor(color) {
        if (hiddenInput) hiddenInput.value = color;
        presets.forEach(b => {
            b.style.border = b.dataset.color === color
                ? '2px solid var(--accent)'
                : '2px solid transparent';
        });
    }

    presets.forEach(btn => {
        btn.addEventListener('click', () => selectColor(btn.dataset.color));
    });

    if (customInput) {
        customInput.addEventListener('input', () => {
            if (hiddenInput) hiddenInput.value = customInput.value;
            presets.forEach(b => b.style.border = '2px solid transparent');
        });
        // Abre o color picker ao clicar no emoji 🎨
        customInput.parentElement.addEventListener('click', () => customInput.click());
    }

    // Quando wallpaper é limpo (usuário remove arquivo), mostra color picker
    const wallInput = document.getElementById('wallpaper');
    if (wallInput) {
        wallInput.addEventListener('change', () => {
            const group = document.getElementById('bg-color-group');
            if (group) group.style.display = wallInput.files.length ? 'none' : 'block';
        });
    }
})();

// ── File: Música ──
const musicInput = document.getElementById('background_music');
if (musicInput) {
    musicInput.addEventListener('change', () => {
        const file = musicInput.files[0];
        if (file) document.getElementById('music-filename').textContent = file.name;
    });
}

// ── File: Conversa ──
const convFileInput = document.getElementById('conversation_file');
if (convFileInput) {
    convFileInput.addEventListener('change', () => {
        const file = convFileInput.files[0];
        if (file) {
            document.getElementById('conv-file-name').textContent = '📄 ' + file.name;
            // Lê o arquivo e estima duração
            const reader = new FileReader();
            reader.onload = e => {
                _lastConvText = e.target.result;
                estimateDuration();
            };
            reader.readAsText(file);
        }
    });
}

// ── File: Imagens da Conversa ──
const imagesInput = document.getElementById('conversation_images');
if (imagesInput) {
    imagesInput.addEventListener('change', () => {
        const files = Array.from(imagesInput.files);
        const countEl = document.getElementById('images-count');
        const previewEl = document.getElementById('images-preview');

        if (countEl) countEl.textContent = files.length + ' imagem(ns) selecionada(s)';
        if (previewEl) {
            previewEl.innerHTML = '';
            files.slice(0, 10).forEach(file => {
                const reader = new FileReader();
                reader.onload = e => {
                    const img = document.createElement('img');
                    img.src = e.target.result;
                    img.title = file.name;
                    previewEl.appendChild(img);
                };
                reader.readAsDataURL(file);
            });
        }
    });
}

// ── Formulário: Submissão ──
const form = document.getElementById('render-form');
if (form) {
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Validação básica
        const title = document.getElementById('title').value.trim();
        if (!title) {
            showToast('❌ Por favor, informe o título do vídeo', 'error');
            return;
        }

        const convText = document.getElementById('conversation_text')?.value.trim();
        const convFile = document.getElementById('conversation_file')?.files[0];
        const activeTab = document.querySelector('.tab.active')?.dataset.tab;
        
        if (activeTab === 'text' && !convText) {
            showToast('❌ Por favor, cole a conversa no campo de texto', 'error');
            return;
        }
        if (activeTab === 'file' && !convFile) {
            showToast('❌ Por favor, selecione um arquivo de conversa', 'error');
            return;
        }

        // Lógica de Modal [IMAGE]
        let textToParse = convText || "";
        if (activeTab === 'file' && convFile) {
            textToParse = await new Promise(resolve => {
                const reader = new FileReader();
                reader.onload = e => resolve(e.target.result);
                reader.readAsText(convFile);
            });
        }

        const imgRegex = /\[IMAGE\]\s+(.+)/gi;
        let matches;
        const requiredImages = [];
        while ((matches = imgRegex.exec(textToParse)) !== null) {
            const name = matches[1].trim();
            if (!requiredImages.includes(name)) requiredImages.push(name);
        }

        if (requiredImages.length > 0) {
            window._pendingFormData = new FormData(form);
            window._pendingFormTab = activeTab;
            showImagesModal(requiredImages);
            return;
        }

        submitGenerateForm(new FormData(form), activeTab);
    });
}

function handleModalImagePreview(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const url = URL.createObjectURL(file);
        const statusSpan = input.parentElement.parentElement.querySelector('.image-status');
        const previewHtml = `<img src="${url}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover; vertical-align: middle; margin-right: 8px;">`;
        if (statusSpan) {
            statusSpan.innerHTML = `${previewHtml} <span style="color: var(--accent);">✅ Arquivo selecionado: ${file.name}</span>`;
            statusSpan.style.color = "";
        } else {
            const infoDiv = input.parentElement.parentElement.querySelector('.image-upload-info');
            infoDiv.innerHTML += `<div class="image-status" style="margin-top: 6px;">${previewHtml} <span style="color: var(--accent);">✅ Selecionado: ${file.name}</span></div>`;
        }
    }
}

function showImagesModal(requiredImages, existingImagesMap = {}) {
    const list = document.getElementById('modal-images-list');
    if (!list) return;
    list.innerHTML = '';
    requiredImages.forEach((name, idx) => {
        const hasExisting = existingImagesMap[name];
        list.innerHTML += `
            <div class="image-upload-row">
                <div class="image-upload-info">
                    <span class="image-tag-name">[IMAGE] ${name}</span>
                    ${hasExisting ? `<div class="image-status" style="margin-top: 6px;"><span style="color:var(--accent);">✅ Arquivo já enviado. Selecione outro para substituir ou deixe vazio para manter.</span></div>` : ''}
                </div>
                <div>
                    <input type="file" id="modal-img-${idx}" class="image-file-input" accept="image/*" data-name="${name}" onchange="handleModalImagePreview(this)">
                </div>
            </div>
        `;
    });
    document.getElementById('images-modal').style.display = 'flex';
}

function closeImagesModal() {
    document.getElementById('images-modal').style.display = 'none';
}

async function confirmImagesModal() {
    const formData = window._pendingFormData;
    if (!formData) return;
    
    // Anexar imagens com o nome exato
    const inputs = document.querySelectorAll('.image-file-input');
    for (let input of inputs) {
        if (input.files.length > 0) {
            const file = input.files[0];
            const name = input.dataset.name;
            const renamedFile = new File([file], name, { type: file.type });
            formData.append('conversation_images', renamedFile);
        }
    }
    
    closeImagesModal();
    
    if (window._submitCallback) {
        window._submitCallback(formData);
    } else {
        submitGenerateForm(formData, window._pendingFormTab);
    }
}

function showUploadingModal(files = []) {
    let modal = document.getElementById('uploading-modal');
    if (modal) {
        modal.remove();
    }
    
    let filesHtml = '';
    if (files && files.length > 0) {
        filesHtml = '<ul id="upload-files-list" style="margin: 8px 0 0 0; padding-left: 20px; font-size: 13px; color: var(--text-muted); list-style: none;">';
        files.forEach((f, idx) => {
            filesHtml += `<li id="file-item-${idx}" style="margin-bottom: 4px; transition: color 0.3s;"><span class="file-icon" style="margin-right: 6px;">⏳</span>${f}</li>`;
        });
        filesHtml += '</ul>';
    }

    modal = document.createElement('div');
    modal.id = 'uploading-modal';
    modal.className = 'modal-overlay';
    modal.innerHTML = `
        <div class="modal-content" style="max-width: 400px;">
            <div class="modal-header">
                <h2>🚀 Preparando Vídeo</h2>
                <p>Por favor aguarde enquanto enviamos seus arquivos...</p>
            </div>
            <div class="modal-body">
                <div class="uploading-steps">
                    <div id="step-1" class="uploading-step active">
                        <span class="uploading-icon"><div class="spinner" style="width:14px;height:14px;border-color:var(--accent);border-top-color:transparent;"></div></span>
                        <span>Analisando requisição e textos...</span>
                    </div>
                    <div id="step-2" class="uploading-step" style="align-items: flex-start;">
                        <span class="uploading-icon" style="flex-shrink: 0;">⚪</span>
                        <div style="display: flex; flex-direction: column;">
                            <span>Fazendo upload de mídias no Drive...</span>
                            ${filesHtml}
                        </div>
                    </div>
                    <div id="step-3" class="uploading-step">
                        <span class="uploading-icon">⚪</span>
                        <span>Colocando na fila de renderização...</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    const steps = modal.querySelectorAll('.uploading-step');
    steps.forEach(s => { s.className = 'uploading-step'; s.querySelector('.uploading-icon').textContent = '⚪'; });
    
    modal.querySelector('#step-1').className = 'uploading-step active';
    modal.querySelector('#step-1 .uploading-icon').innerHTML = '<div class="spinner" style="width:14px;height:14px;border-color:var(--accent);border-top-color:transparent;"></div>';
    modal.style.display = 'flex';
    
    // Lista de timeouts para cancelar no complete
    window._fileUploadTimers = [];
    
    window._uploadTimer = setTimeout(() => {
        modal.querySelector('#step-1').className = 'uploading-step done';
        modal.querySelector('#step-1 .uploading-icon').textContent = '✅';
        modal.querySelector('#step-2').className = 'uploading-step active';
        modal.querySelector('#step-2 .uploading-icon').innerHTML = '<div class="spinner" style="width:14px;height:14px;border-color:var(--accent);border-top-color:transparent;"></div>';
        
        const fileItems = modal.querySelectorAll('#upload-files-list li');
        if (fileItems.length > 0) {
            let delay = 0;
            // Anima todos exceto o último, que só conclui quando a requisição terminar de verdade
            for (let i = 0; i < fileItems.length - 1; i++) {
                delay += 1500; // 1.5s por arquivo
                const timerId = setTimeout(() => {
                    fileItems[i].style.color = 'var(--accent)';
                    fileItems[i].querySelector('.file-icon').textContent = '✅';
                }, delay);
                window._fileUploadTimers.push(timerId);
            }
        }
    }, 1200);
}

function completeUploadingModal(callback) {
    const modal = document.getElementById('uploading-modal');
    if (!modal) return;
    clearTimeout(window._uploadTimer);
    if (window._fileUploadTimers) {
        window._fileUploadTimers.forEach(t => clearTimeout(t));
    }
    
    const fileItems = modal.querySelectorAll('#upload-files-list li');
    fileItems.forEach(li => {
        li.style.color = 'var(--accent)';
        li.querySelector('.file-icon').textContent = '✅';
    });
    
    modal.querySelector('#step-2').className = 'uploading-step done';
    modal.querySelector('#step-2 .uploading-icon').textContent = '✅';
    modal.querySelector('#step-3').className = 'uploading-step done';
    modal.querySelector('#step-3 .uploading-icon').textContent = '✅';
    
    setTimeout(() => {
        modal.style.display = 'none';
        if (callback) callback();
        const ps = document.getElementById('progress-section');
        if (ps) {
            ps.style.display = 'block';
            window.scrollTo({ top: ps.offsetTop - 100, behavior: 'smooth' });
        }
    }, 800);
}

async function submitGenerateForm(formData, activeTab) {
    const btn = document.getElementById('btn-generate');
    const btnText = btn.querySelector('.btn-text');
    
    if (activeTab === 'text') formData.delete('conversation_file');
    if (activeTab === 'file') formData.delete('conversation_text');
    
    const uploadedFiles = [];
    for (let [key, value] of formData.entries()) {
        if (value instanceof File && value.size > 0 && value.name) {
            uploadedFiles.push(value.name);
        }
    }
    
    btn.disabled = true;
    showUploadingModal(uploadedFiles);

    try {
        const res = await fetch('/whatsapp/render', { method: 'POST', body: formData });
        const data = await res.json();

        completeUploadingModal(() => {
            if (!res.ok || data.error) {
                showToast('❌ ' + (data.error || 'Erro ao criar job'), 'error');
                return;
            }
            const jobId = data.job_id;
            const title = formData.get('title');
            showToast(`✅ Job #${jobId} criado! Aguardando worker...`, 'success');
            startProgressTracking(jobId, title);
        });

    } catch (err) {
        completeUploadingModal();
        showToast('❌ Erro de rede: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btnText.textContent = 'Gerar Vídeo';
        btn.querySelector('.btn-icon').textContent = '🎬';
    }
}

// ── SSE Global de Progresso — 1 conexão por sessão de navegador ──
const _trackedJobs = {};   // { [jobId]: { title } }
let _progressSSE = null;
let _sseRetryTimeout = null;

function initProgressStream() {
    if (_progressSSE && _progressSSE.readyState !== EventSource.CLOSED) return;

    _progressSSE = new EventSource('/api/progress/stream');

    _progressSSE.onopen = () => {
        if (_sseRetryTimeout) { clearTimeout(_sseRetryTimeout); _sseRetryTimeout = null; }
    };

    _progressSSE.onmessage = (e) => {
        let data;
        try { data = JSON.parse(e.data); } catch { return; }

        const jobId = data.job_id;
        if (!jobId || !_trackedJobs[jobId]) return;  // job não monitorado nesta sessão

        updateProgressCard(jobId, data, _trackedJobs[jobId].title);
    };

    _progressSSE.onerror = () => {
        _progressSSE.close();
        _progressSSE = null;
        // Tentar reconectar após 4s se ainda há jobs sendo monitorados
        if (Object.keys(_trackedJobs).length > 0) {
            _sseRetryTimeout = setTimeout(initProgressStream, 4000);
        }
    };
}

// ── Progresso: criar card e registrar job ──
function startProgressTracking(jobId, title) {
    const section = document.getElementById('progress-section');
    const container = document.getElementById('progress-container');
    section.style.display = 'block';
    section.scrollIntoView({ behavior: 'smooth' });

    // Criar card de progresso
    const card = document.createElement('div');
    card.className = 'progress-item';
    card.id = `progress-${jobId}`;
    card.innerHTML = `
        <div class="progress-header">
            <span class="progress-title">🎬 ${title} <span style="color:var(--text-muted);font-weight:400;font-size:12px;">#${jobId}</span></span>
            <span class="progress-percent" id="pct-${jobId}">0%</span>
        </div>
        <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="bar-${jobId}" style="width:0%"></div>
        </div>
        <div class="progress-detail" id="det-${jobId}">Aguardando worker...</div>
    `;
    container.prepend(card);

    // Registrar no mapa de jobs monitorados
    _trackedJobs[jobId] = { title };

    // Garantir que o SSE global está aberto
    initProgressStream();
}

// ── Atualizar card de um job específico ──
function updateProgressCard(jobId, data, title) {
    const pct = Math.round(data.progress || 0);
    const pctEl = document.getElementById(`pct-${jobId}`);
    if (!pctEl) return;

    pctEl.textContent = pct + '%';
    document.getElementById(`bar-${jobId}`).style.width = pct + '%';
    document.getElementById(`det-${jobId}`).textContent = data.detail || '';

    if (data.status === 'done') {
        const card = document.getElementById(`progress-${jobId}`);
        card.innerHTML += `
            <div class="progress-done">
                <span>✅ Vídeo pronto!</span>
                <a href="/whatsapp/video/${jobId}" class="btn btn-download">🔍 Ver Detalhes</a>
            </div>
        `;
        addJobToList(jobId, title || _trackedJobs[jobId]?.title || '', data.video_type || 'whatsapp');
        showToast('🎉 Vídeo gerado com sucesso!', 'success');
        delete _trackedJobs[jobId];
        if (Object.keys(_trackedJobs).length === 0 && _progressSSE) {
            _progressSSE.close();
            _progressSSE = null;
        }
    }

    if (data.status === 'error') {
        const card = document.getElementById(`progress-${jobId}`);
        card.innerHTML += `<div class="progress-error">❌ ${data.error || 'Erro na renderização'}</div>`;
        showToast('❌ Erro ao gerar vídeo', 'error');
        delete _trackedJobs[jobId];
        if (Object.keys(_trackedJobs).length === 0 && _progressSSE) {
            _progressSSE.close();
            _progressSSE = null;
        }
    }
}

// ── Adicionar Job à Lista ──
function addJobToList(jobId, title, videoType) {
    const list = document.getElementById('jobs-list');
    const empty = list.querySelector('.jobs-empty');
    if (empty) empty.remove();

    const item = document.createElement('div');
    item.className = 'job-item';
    item.dataset.jobId = jobId;
    item.innerHTML = `
        <div class="job-info">
            <span class="job-name">${title}</span>
            <span class="job-id">#${jobId}</span>
            <span class="job-type-badge">${videoType}</span>
        </div>
        <div class="job-actions">
            <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 13px;" onclick="openDuplicateModal('${jobId}', '${title}')">📄 Duplicar</button>
            <a href="/whatsapp/video/${jobId}" class="btn btn-detail">🔍 Detalhes</a>
            <button class="btn btn-delete" onclick="deleteJob('${jobId}')">🗑️</button>
        </div>
    `;
    list.prepend(item);
}

// ── Deletar Job ──
let currentDeleteJobId = null;

function deleteJob(jobId) {
    currentDeleteJobId = jobId;
    document.getElementById('delete-modal').style.display = 'flex';
}

function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    currentDeleteJobId = null;
}

async function submitDelete() {
    if (!currentDeleteJobId) return;
    const jobId = currentDeleteJobId;
    closeDeleteModal();
    
    showToast('Processando exclusão...', 'info');
    
    try {
        const res = await fetch(`/api/jobs/${jobId}?delete_drive=true`, { method: 'DELETE' });
        if (res.ok) {
            document.querySelector(`[data-job-id="${jobId}"]`)?.remove();
            showToast('🗑️ Vídeo excluído permanentemente!', 'success');
        } else {
            const data = await res.json();
            showToast('❌ Erro ao excluir: ' + (data.error || ''), 'error');
        }
    } catch(e) {
        showToast('❌ Erro de rede ao excluir', 'error');
    }
}

// ── Toast ──
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// ── Duplicação de Job ──
let currentDupJobId = null;

async function openDuplicateModal(jobId, oldTitle) {
    currentDupJobId = jobId;
    document.getElementById('duplicate-modal').style.display = 'flex';
    document.getElementById('dup-new-title').value = oldTitle + ' (Cópia)';
    const listContainer = document.getElementById('dup-files-list');
    listContainer.innerHTML = '<span style="color:var(--text-muted); font-size: 13px;">Buscando arquivos no Drive... ⏳</span>';
    document.getElementById('btn-confirm-dup').disabled = true;

    try {
        const res = await fetch(`/api/jobs/${jobId}/details`);
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        listContainer.innerHTML = '';
        const files = data.files || {};
        
        if (Object.keys(files).length === 0) {
            listContainer.innerHTML = '<span style="color:var(--text-muted); font-size: 13px;">Nenhum arquivo encontrado.</span>';
        } else {
            for (const [key, fileId] of Object.entries(files)) {
                if (key.endsWith('_ext') || key === 'imagens_folder_id') continue;
                
                listContainer.innerHTML += `
                    <label style="display:flex; align-items:center; gap:10px; cursor:pointer; font-size:14px; background: rgba(255,255,255,0.03); padding: 10px 12px; border-radius: 6px; border: 1px solid transparent; transition: all 0.2s;" onmouseover="this.style.background='rgba(255,255,255,0.06)'" onmouseout="this.style.background='rgba(255,255,255,0.03)'">
                        <input type="checkbox" class="dup-file-cb" value="${key}" checked style="width: 16px; height: 16px; accent-color: var(--accent);">
                        <span style="font-weight: 500;">${key}</span>
                    </label>
                `;
            }
        }
        document.getElementById('btn-confirm-dup').disabled = false;
    } catch (err) {
        listContainer.innerHTML = `<span style="color:var(--danger); font-size: 13px;">Erro: ${err.message}</span>`;
    }
}

function closeDuplicateModal() {
    document.getElementById('duplicate-modal').style.display = 'none';
}

async function submitDuplicate() {
    if (!currentDupJobId) return;
    const btn = document.getElementById('btn-confirm-dup');
    btn.disabled = true;

    const newTitle = document.getElementById('dup-new-title').value;
    const checkboxes = document.querySelectorAll('.dup-file-cb:checked');
    const filesToCopy = Array.from(checkboxes).map(cb => cb.value);

    closeDuplicateModal();
    
    showUploadingModal(filesToCopy);
    const modal = document.getElementById('uploading-modal');
    if (modal) {
        modal.querySelector('h2').textContent = "🚀 Duplicando Vídeo";
        modal.querySelector('p').textContent = "Copiando arquivos no Google Drive...";
        const steps = modal.querySelectorAll('.uploading-step');
        if (steps.length >= 3) {
            steps[0].querySelector('span:nth-child(2)').textContent = "Lendo projeto original...";
            steps[1].querySelector('div span:nth-child(1)').textContent = "Copiando arquivos selecionados...";
            steps[2].querySelector('span:nth-child(2)').textContent = "Finalizando duplicação...";
        }
    }

    try {
        const res = await fetch(`/whatsapp/video/${currentDupJobId}/duplicate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ new_title: newTitle, files_to_copy: filesToCopy })
        });
        const data = await res.json();
        
        completeUploadingModal(() => {
            if (data.job_id) {
                showToast('✅ Job duplicado com sucesso!', 'success');
                setTimeout(() => location.reload(), 1500);
            } else {
                showToast('❌ Erro: ' + data.error, 'error');
            }
        });
    } catch(e) {
        completeUploadingModal(() => {
            showToast('❌ Erro de rede ao duplicar', 'error');
        });
    } finally {
        btn.disabled = false;
        btn.querySelector('.btn-text').textContent = "Confirmar Duplicação";
    }
}

// ── Simulador de Duração ──
let _lastConvText = '';
let _estimateTimer = null;

// Conecta o textarea ao estimador
(function () {
    const ta = document.getElementById('conversation_text');
    if (ta) {
        ta.addEventListener('input', () => {
            _lastConvText = ta.value;
            clearTimeout(_estimateTimer);
            _estimateTimer = setTimeout(estimateDuration, 400); // debounce 400ms
        });
    }
})();

/**
 * Estima a duração do vídeo com base na conversa e nas configurações atuais.
 * Espelha a lógica do animator.py (Timeline._build_timeline) em JS.
 */
function estimateDuration() {
    const text = _lastConvText.trim();
    const estimatorEl = document.getElementById('duration-estimator');
    if (!estimatorEl) return;

    if (!text) {
        estimatorEl.style.display = 'none';
        return;
    }

    // Ler configurações atuais
    const speed        = parseFloat(document.getElementById('speed')?.value || 1.0);
    const readingSpeed = parseFloat(document.getElementById('reading_speed')?.value || 1.0);
    const scrollSpeed  = parseFloat(document.getElementById('scroll_speed')?.value || 1.0);
    const animStyle    = document.getElementById('animation_style')?.value || 'fade';

    // Parsear mensagens (mesmo padrão do parser.py)
    const msgPattern  = /^\[(\d{1,2}:\d{2})\]\s+(.+?):\s+(.+)$/;
    const cmdPattern  = /^\[(IMAGE|EMOJI|AUDIO|DATE)\]\s+(.+)$/i;

    const lines = text.split('\n');
    const messages = [];

    for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line) continue;

        const cmd = line.match(cmdPattern);
        if (cmd) {
            const t = cmd[1].toUpperCase();
            if (t === 'IMAGE')  messages.push({ type: 'image',          text: '' });
            if (t === 'EMOJI')  messages.push({ type: 'emoji',          text: cmd[2] });
            if (t === 'AUDIO')  messages.push({ type: 'audio',          text: '' });
            if (t === 'DATE')   messages.push({ type: 'date_separator', text: cmd[2] });
            continue;
        }

        const msg = line.match(msgPattern);
        if (msg) {
            messages.push({ type: 'text', text: msg[3], sender: msg[2] });
        }
    }

    if (messages.length === 0) {
        estimatorEl.style.display = 'none';
        return;
    }

    // Contar tipos
    let imgCount  = messages.filter(m => m.type === 'image').length;
    let dateCount = messages.filter(m => m.type === 'date_separator').length;
    let textCount = messages.filter(m => m.type === 'text' || m.type === 'emoji').length;

    // ── Simulação da timeline (simplificada) ──
    // Valores médios usados no Python (sem humanize):
    const TYPING_DUR   = 600;  // média de min(500+len*15, 2000) para texto médio
    let currentTime = 500;

    for (const msg of messages) {
        // Delay de chegada
        let delay;
        if (msg.type === 'date_separator') delay = 300;
        else if (msg.type === 'image')     delay = 2000;
        else if (msg.type === 'audio')     delay = 1800;
        else if (msg.type === 'emoji')     delay = 600;
        else {
            const len = (msg.text || '').length;
            if (len > 100) delay = 2200;
            else if (len > 50) delay = 1600;
            else delay = 1000;
        }
        currentTime += delay / speed;

        // Animação de digitação (apenas para mensagens recebidas em modo typing)
        if (animStyle === 'typing' && msg.type === 'text' && msg.sender !== 'me') {
            const len = (msg.text || '').length;
            const typingDur = Math.min(500 + len * 15, 2000);
            currentTime += typingDur / speed;
        }

        // Aparecer (350ms de animação)
        currentTime += 350;

        // Pausa de leitura
        let readPause;
        if (msg.type === 'date_separator') readPause = 200;
        else if (msg.type === 'image')     readPause = 2500;
        else if (msg.type === 'audio')     readPause = 2000;
        else {
            const len = (msg.text || '').length;
            if (len > 100) readPause = 2000;
            else if (len > 50) readPause = 1500;
            else readPause = 800;
        }
        currentTime += readPause / readingSpeed;
    }

    // Buffer final de 5s
    const totalMs = currentTime + 5000;
    const totalSec = Math.ceil(totalMs / 1000);

    // Formatar
    const mins = Math.floor(totalSec / 60);
    const secs = totalSec % 60;
    const formatted = mins > 0
        ? `${mins}m ${secs.toString().padStart(2, '0')}s`
        : `${secs}s`;

    // Atualizar UI
    document.getElementById('duration-value').textContent = formatted;
    document.getElementById('est-msg-count').textContent = messages.length;
    document.getElementById('est-img-count').textContent = imgCount;
    document.getElementById('est-date-count').textContent = dateCount;
    document.getElementById('est-speed-val').textContent = speed.toFixed(1) + 'x';
    estimatorEl.style.display = 'block';
}
