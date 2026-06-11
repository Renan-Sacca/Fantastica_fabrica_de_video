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
        if (!file) return;
        const preview = document.getElementById('wallpaper-preview');
        const reader = new FileReader();
        reader.onload = e => {
            preview.innerHTML = `<img src="${e.target.result}" alt="Papel de parede">`;
        };
        reader.readAsDataURL(file);
    });
}

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
        if (file) document.getElementById('conv-file-name').textContent = '📄 ' + file.name;
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
        const btn = document.getElementById('btn-generate');
        const btnText = btn.querySelector('.btn-text');

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

        // UI: loading
        btn.disabled = true;
        btnText.textContent = 'Enviando para o Drive...';
        btn.querySelector('.btn-icon').textContent = '⏳';

        try {
            const formData = new FormData(form);

            // Remover campo da aba inativa
            if (activeTab === 'text') formData.delete('conversation_file');
            if (activeTab === 'file') formData.delete('conversation_text');

            const res = await fetch('/render', { method: 'POST', body: formData });
            const data = await res.json();

            if (!res.ok || data.error) {
                showToast('❌ ' + (data.error || 'Erro ao criar job'), 'error');
                return;
            }

            // Sucesso: mostrar progresso
            const jobId = data.job_id;
            showToast(`✅ Job #${jobId} criado! Aguardando worker...`, 'success');
            startProgressTracking(jobId, title);
            form.reset();

        } catch (err) {
            showToast('❌ Erro de rede: ' + err.message, 'error');
        } finally {
            btn.disabled = false;
            btnText.textContent = 'Gerar Vídeo';
            btn.querySelector('.btn-icon').textContent = '🎬';
        }
    });
}

// ── Progresso via SSE ──
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

    // SSE
    const es = new EventSource(`/api/jobs/${jobId}/stream`);

    es.onmessage = (e) => {
        const data = JSON.parse(e.data);
        const pct = Math.round(data.progress || 0);

        document.getElementById(`pct-${jobId}`).textContent = pct + '%';
        document.getElementById(`bar-${jobId}`).style.width = pct + '%';
        document.getElementById(`det-${jobId}`).textContent = data.detail || '';

        if (data.status === 'done') {
            es.close();
            card.innerHTML += `
                <div class="progress-done">
                    <span>✅ Vídeo pronto!</span>
                    <a href="/video/${jobId}" class="btn btn-download">🔍 Ver Detalhes</a>
                </div>
            `;
            addJobToList(jobId, title, data.video_type || 'whatsapp');
            showToast('🎉 Vídeo gerado com sucesso!', 'success');
        }

        if (data.status === 'error') {
            es.close();
            card.innerHTML += `<div class="progress-error">❌ ${data.error || 'Erro na renderização'}</div>`;
            showToast('❌ Erro ao gerar vídeo', 'error');
        }
    };

    es.onerror = () => {
        es.close();
        document.getElementById(`det-${jobId}`).textContent = 'Conexão SSE perdida. Verifique os Detalhes.';
    };
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
            <a href="/video/${jobId}" class="btn btn-detail">🔍 Detalhes</a>
            <button class="btn btn-delete" onclick="deleteJob('${jobId}')">🗑️</button>
        </div>
    `;
    list.prepend(item);
}

// ── Deletar Job ──
async function deleteJob(jobId) {
    if (!confirm('Remover este job do histórico local?')) return;
    const res = await fetch(`/api/jobs/${jobId}`, { method: 'DELETE' });
    if (res.ok) {
        document.querySelector(`[data-job-id="${jobId}"]`)?.remove();
        showToast('🗑️ Job removido', 'info');
    } else {
        showToast('❌ Erro ao remover job', 'error');
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
