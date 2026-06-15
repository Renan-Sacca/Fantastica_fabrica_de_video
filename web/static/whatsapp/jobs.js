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

let currentDeleteJobId = null;

function deleteJob(jobId) {
    currentDeleteJobId = jobId;
    document.getElementById('delete-modal').style.display = 'flex';
}

function closeDeleteModal() {
    document.getElementById('delete-modal').style.display = 'none';
    currentDeleteJobId = null;
}

async function submitDelete(deleteFromDrive) {
    if (!currentDeleteJobId) return;
    const jobId = currentDeleteJobId;
    closeDeleteModal();
    
    showToast('Processando exclusão...', 'info');
    
    try {
        const res = await fetch(`/api/jobs/${jobId}?delete_drive=${deleteFromDrive}`, { method: 'DELETE' });
        if (res.ok) {
            document.querySelector(`[data-job-id="${jobId}"]`)?.remove();
            showToast('🗑️ Job removido com sucesso!', 'success');
        } else {
            const data = await res.json();
            showToast('❌ Erro ao remover job: ' + (data.error || ''), 'error');
        }
    } catch(e) {
        showToast('❌ Erro de rede ao remover', 'error');
    }
}

function filterJobs() {
    const query = document.getElementById('job-search').value.toLowerCase();
    const items = document.querySelectorAll('.job-item');
    
    items.forEach(item => {
        const name = item.querySelector('.job-name').textContent.toLowerCase();
        const id = item.querySelector('.job-id').textContent.toLowerCase();
        
        if (name.includes(query) || id.includes(query)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

function syncDrive() {
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.innerHTML = 'Sincronizando...';
    fetch('/api/sync', { method: 'POST' })
        .then(res => {
            if(res.ok) window.location.reload();
            else alert('Erro ao sincronizar');
        })
        .catch(e => alert('Erro de rede ao sincronizar'))
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.92-10.26l5.08 5.08"/></svg> Sincronizar';
        });
}
