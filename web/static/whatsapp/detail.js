function handleFilePreview(input, type) {
    const container = input.nextElementSibling;
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const url = URL.createObjectURL(file);
        const parent = input.parentElement;
        
        if (type === 'image') {
            container.innerHTML = `
                <div class="file-upload-preview"><img src="${url}" /></div>
                <span class="file-upload-text" style="color: var(--accent);">✅ ${file.name} selecionado</span>
            `;
        } else if (type === 'audio') {
            container.innerHTML = `
                <span class="upload-placeholder" style="font-size:24px; color: var(--accent);">🎵</span>
                <span class="file-upload-text" style="color: var(--accent);">✅ ${file.name} selecionado</span>
            `;
            let audioContainer = parent.nextElementSibling;
            let audioTag = audioContainer.querySelector('audio');
            if (!audioTag) {
                audioTag = document.createElement('audio');
                audioTag.controls = true;
                audioTag.style.width = '100%';
                audioTag.style.marginTop = '10px';
                audioTag.style.height = '30px';
                audioContainer.appendChild(audioTag);
            }
            audioTag.src = url;
        }
    }
}

function handleModalImagePreview(input) {
    if (input.files && input.files[0]) {
        const file = input.files[0];
        const url = URL.createObjectURL(file);
        const statusSpan = input.parentElement.parentElement.querySelector('.image-status');
        const previewHtml = `<img src="${url}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover; vertical-align: middle; margin-right: 8px;">`;
        statusSpan.innerHTML = `${previewHtml} <span style="color: var(--accent);">✅ Substituído por: ${file.name}</span>`;
        statusSpan.style.color = "";
    }
}

function showImagesModal(requiredImages) {
    const list = document.getElementById('modal-images-list');
    list.innerHTML = '';
    requiredImages.forEach((name, idx) => {
        const existingId = JOB_IMAGES[name];
        let statusHtml = '';
        if (existingId) {
            statusHtml = `
                <img src="/api/drive/media/${existingId}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover; vertical-align: middle; margin-right: 8px;">
                <span style="color:var(--accent);">✅ Arquivo no Drive. Substitua ou deixe vazio para manter.</span>
            `;
        } else {
            statusHtml = `<span style="color:var(--warning)">⚠️ Nova imagem. É necessário enviar o arquivo.</span>`;
        }
        
        list.innerHTML += `
            <div class="image-upload-row">
                <div class="image-upload-info">
                    <span class="image-tag-name">[IMAGE] ${name}</span>
                    <div class="image-status" style="margin-top: 6px;">${statusHtml}</div>
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
    const btn = document.getElementById("btn-recreate");
    btn.disabled = false;
    btn.querySelector('.btn-text').textContent = "Salvar Edições e Recriar Vídeo";
}

async function confirmImagesModal() {
    const formData = window._pendingFormData;
    const requiredImages = window._requiredImages;
    if (!formData) return;
    
    formData.append('active_image_names', JSON.stringify(requiredImages));
    
    const inputs = document.querySelectorAll('.image-file-input');
    for (let input of inputs) {
        const name = input.dataset.name;
        if (input.files.length > 0) {
            const file = input.files[0];
            const renamedFile = new File([file], name, { type: file.type });
            formData.append('conversation_images', renamedFile);
        } else if (!JOB_IMAGES[name]) {
            showToast(`❌ Você precisa selecionar um arquivo para [IMAGE] ${name}`, "error");
            return;
        }
    }
    
    closeImagesModal();
    await submitRecreate(formData);
}

async function recriarVideo(e, jobId) {
    e.preventDefault();
    const btn = document.getElementById("btn-recreate");
    const btnText = btn.querySelector('.btn-text');
    
    btn.disabled = true;
    btnText.textContent = "Verificando e montando requisição...";

    const formData = new FormData(e.target);
    const convText = formData.get('conversation_text') || "";
    
    const imgRegex = /\[IMAGE\]\s+(.+)/gi;
    let matches;
    const requiredImages = [];
    while ((matches = imgRegex.exec(convText)) !== null) {
        const name = matches[1].trim();
        if (!requiredImages.includes(name)) requiredImages.push(name);
    }

    window._pendingFormData = formData;
    window._requiredImages = requiredImages;
    
    if (requiredImages.length > 0) {
        showImagesModal(requiredImages);
        return;
    }

    formData.append('active_image_names', "[]");
    await submitRecreate(formData);
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
                <h2>🚀 Preparando Edição</h2>
                <p>Por favor aguarde enquanto atualizamos seus arquivos...</p>
            </div>
            <div class="modal-body">
                <div class="uploading-steps">
                    <div id="step-1" class="uploading-step active">
                        <span class="uploading-icon"><div class="spinner" style="width:14px;height:14px;border-color:var(--accent);border-top-color:transparent;"></div></span>
                        <span>Verificando alterações...</span>
                    </div>
                    <div id="step-2" class="uploading-step" style="align-items: flex-start;">
                        <span class="uploading-icon" style="flex-shrink: 0;">⚪</span>
                        <div style="display: flex; flex-direction: column;">
                            <span>Substituindo mídias no Drive...</span>
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
    
    window._fileUploadTimers = [];
    
    window._uploadTimer = setTimeout(() => {
        modal.querySelector('#step-1').className = 'uploading-step done';
        modal.querySelector('#step-1 .uploading-icon').textContent = '✅';
        modal.querySelector('#step-2').className = 'uploading-step active';
        modal.querySelector('#step-2 .uploading-icon').innerHTML = '<div class="spinner" style="width:14px;height:14px;border-color:var(--accent);border-top-color:transparent;"></div>';
        
        const fileItems = modal.querySelectorAll('#upload-files-list li');
        if (fileItems.length > 0) {
            let delay = 0;
            for (let i = 0; i < fileItems.length - 1; i++) {
                delay += 1500;
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
    }, 800);
}

async function submitRecreate(formData) {
    const btn = document.getElementById("btn-recreate");
    const btnText = btn.querySelector('.btn-text');
    
    const uploadedFiles = [];
    for (let [key, value] of formData.entries()) {
        if (value instanceof File && value.size > 0 && value.name) {
            uploadedFiles.push(value.name);
        }
    }
    
    btn.disabled = true;
    showUploadingModal(uploadedFiles);
    
    try {
        const res = await fetch(`/whatsapp/video/${JOB_ID}/edit`, { 
            method: "POST",
            body: formData 
        });
        const data = await res.json();
        
        completeUploadingModal(() => {
            if (data.job_id) {
                showToast("✅ Edições salvas! Iniciando nova renderização...", "success");
                setTimeout(() => location.reload(), 1500);
            } else {
                showToast("❌ " + (data.error || "Erro ao recriar"), "error");
                btn.disabled = false;
                btnText.textContent = "Salvar Edições e Recriar Vídeo";
            }
        });
    } catch (err) {
        completeUploadingModal();
        showToast("❌ Erro de rede: " + err.message, "error");
        btn.disabled = false;
        btnText.textContent = "Salvar Edições e Recriar Vídeo";
    }
}

function showToast(msg, type = "info") {
    const t = document.createElement("div");
    t.className = `toast ${type}`;
    t.textContent = msg;
    document.getElementById("toast-container").appendChild(t);
    setTimeout(() => t.remove(), 4000);
}

document.addEventListener("DOMContentLoaded", () => {
    if (typeof JOB_STATUS !== 'undefined' && typeof JOB_ID !== 'undefined') {
        if (!["done", "error", "draft"].includes(JOB_STATUS)) {
            const btn = document.getElementById("btn-recreate");
            if (btn) btn.disabled = true;
            
            const evtSource = new EventSource(`/api/jobs/${JOB_ID}/stream`);
            evtSource.onmessage = (e) => {
                const data = JSON.parse(e.data);
                const pctEl = document.getElementById("detail-percent");
                const detEl = document.getElementById("detail-detail");
                const barEl = document.getElementById("detail-bar");
                const badgeEl = document.getElementById("status-badge");
                const progDiv = document.getElementById("detail-progress");

                if (pctEl) pctEl.textContent = Math.round(data.progress) + "%";
                if (detEl) detEl.textContent = data.detail || "";
                if (barEl) barEl.style.width = data.progress + "%";
                if (badgeEl) {
                    badgeEl.textContent = data.status;
                    badgeEl.className = "job-status-badge " + data.status;
                }

                if (data.status === "done" || data.status === "error") {
                    evtSource.close();
                    if (progDiv) progDiv.style.display = "none";
                    if (btn) btn.disabled = false;
                    if (data.status === "done") {
                        setTimeout(() => location.reload(), 1000);
                    }
                }
            };
        }
    }
});

// ── Correção de Texto com IA ──
async function corrigirConversaComIA() {
    const rawText = document.getElementById("conversation_text").value;
    if (!rawText.trim()) {
        showToast("❌ Digite ou cole uma conversa antes de corrigir.", "error");
        return;
    }
    
    const provider = document.getElementById("ai-provider").value;
    const btn = document.getElementById("btn-correct-text");
    const btnLabel = document.getElementById("btn-correct-text-label");
    const progContainer = document.getElementById("ai-progress-container");
    const progStatus = document.getElementById("ai-progress-status");
    const progBar = document.getElementById("ai-progress-bar");
    
    // Desabilitar UI
    btn.disabled = true;
    btnLabel.textContent = "Corrigindo...";
    progContainer.style.display = "block";
    progStatus.textContent = "Iniciando correção (" + provider + ")...";
    progBar.style.width = "10%";
    
    try {
        const formData = new FormData();
        formData.append("raw_text", rawText);
        formData.append("provider", provider);
        
        const res = await fetch("/whatsapp/correct-text", {
            method: "POST",
            body: formData
        });
        
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || "Erro ao solicitar correção");
        }
        
        const jobId = data.job_id;
        progBar.style.width = "30%";
        progStatus.textContent = "Job enviado para a fila do agente...";
        
        // Conectar ao stream SSE
        const eventSource = new EventSource(`/api/correction/${jobId}/stream`);
        let progressVal = 30;
        
        eventSource.onmessage = async (e) => {
            try {
                const sseData = JSON.parse(e.data);
                
                if (sseData.status === "processing") {
                    progressVal = Math.min(progressVal + 15, 80);
                    progBar.style.width = progressVal + "%";
                    progStatus.textContent = sseData.detail || "Corrigindo texto...";
                } else if (sseData.status === "done") {
                    eventSource.close();
                    progBar.style.width = "100%";
                    progStatus.textContent = "Correção finalizada!";
                    
                    // Buscar o resultado corrigido
                    const resultRes = await fetch(`/whatsapp/correct-text/${jobId}`);
                    const resultData = await resultRes.json();
                    
                    if (resultData.corrected_text) {
                        document.getElementById("conversation_text").value = resultData.corrected_text;
                        showToast("✅ Conversa corrigida com sucesso!", "success");
                    } else {
                        showToast("❌ Erro ao buscar texto corrigido.", "error");
                    }
                    
                    // Resetar UI após 3 segundos
                    setTimeout(() => {
                        progContainer.style.display = "none";
                        btn.disabled = false;
                        btnLabel.textContent = "Corrigir com IA";
                    }, 3000);
                    
                } else if (sseData.status === "error") {
                    eventSource.close();
                    throw new Error(sseData.detail || sseData.error || "Erro no processamento da IA");
                }
            } catch (err) {
                eventSource.close();
                handleCorrectionError(err.message, btn, btnLabel, progContainer);
            }
        };
        
        eventSource.onerror = () => {
            eventSource.close();
            // Tentar buscar direto do endpoint como fallback
            fallbackFetchCorrection(jobId, btn, btnLabel, progContainer, progStatus, progBar);
        };
        
    } catch (err) {
        handleCorrectionError(err.message, btn, btnLabel, progContainer);
    }
}

function handleCorrectionError(msg, btn, btnLabel, progContainer) {
    showToast("❌ " + msg, "error");
    progContainer.style.display = "none";
    btn.disabled = false;
    btnLabel.textContent = "Corrigir com IA";
}

async function fallbackFetchCorrection(jobId, btn, btnLabel, progContainer, progStatus, progBar) {
    progStatus.textContent = "SSE desconectado. Monitorando status via banco...";
    progBar.style.width = "50%";
    
    // Polling simples de fallback
    for (let i = 0; i < 30; i++) {
        await new Promise(resolve => setTimeout(resolve, 3000));
        try {
            const res = await fetch(`/whatsapp/correct-text/${jobId}`);
            if (!res.ok) continue;
            const data = await res.json();
            
            if (data.status === "done") {
                progBar.style.width = "100%";
                progStatus.textContent = "Correção finalizada!";
                if (data.corrected_text) {
                    document.getElementById("conversation_text").value = data.corrected_text;
                    showToast("✅ Conversa corrigida com sucesso!", "success");
                }
                break;
            } else if (data.status === "error") {
                handleCorrectionError(data.error || "Erro na correção de texto.", btn, btnLabel, progContainer);
                return;
            }
        } catch (e) {}
    }
    
    progContainer.style.display = "none";
    btn.disabled = false;
    btnLabel.textContent = "Corrigir com IA";
}
