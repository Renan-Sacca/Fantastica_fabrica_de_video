/**
 * Dashboard JavaScript
 * Handles form submission, file previews, SSE progress, and toast notifications.
 */
(function () {
    'use strict';

    // ── DOM References ──
    const form = document.getElementById('render-form');
    const btnGenerate = document.getElementById('btn-generate');
    const progressSection = document.getElementById('progress-section');
    const progressContainer = document.getElementById('progress-container');
    const toastContainer = document.getElementById('toast-container');
    const jobsList = document.getElementById('jobs-list');

    // File previews
    const photoInput = document.getElementById('contact_photo');
    const photoPreview = document.getElementById('photo-preview');
    const wallpaperInput = document.getElementById('wallpaper');
    const wallpaperPreview = document.getElementById('wallpaper-preview');
    const musicInput = document.getElementById('background_music');
    const musicFilename = document.getElementById('music-filename');
    const convFileInput = document.getElementById('conversation_file');
    const convFileName = document.getElementById('conv-file-name');

    // Range sliders
    const rangeInputs = document.querySelectorAll('input[type="range"]');

    // Tabs
    const tabs = document.querySelectorAll('.tab');

    // ── Toast Notifications ──
    function showToast(message, type = 'error', duration = 5000) {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);

        setTimeout(function () {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(20px)';
            toast.style.transition = 'all 0.3s ease';
            setTimeout(function () { toast.remove(); }, 300);
        }, duration);
    }

    // ── File Preview Handlers ──
    function setupImagePreview(input, previewEl, circular) {
        input.addEventListener('change', function () {
            const file = input.files[0];
            if (!file) return;

            if (!file.type.startsWith('image/')) {
                showToast('Por favor, selecione uma imagem válida.', 'error');
                return;
            }

            const reader = new FileReader();
            reader.onload = function (e) {
                const img = document.createElement('img');
                img.src = e.target.result;
                previewEl.innerHTML = '';
                previewEl.appendChild(img);
            };
            reader.readAsDataURL(file);
        });
    }

    setupImagePreview(photoInput, photoPreview, true);
    setupImagePreview(wallpaperInput, wallpaperPreview, false);

    // Music filename display
    musicInput.addEventListener('change', function () {
        if (musicInput.files[0]) {
            musicFilename.textContent = '🎵 ' + musicInput.files[0].name;
        }
    });

    // Conversation file display
    convFileInput.addEventListener('change', function () {
        if (convFileInput.files[0]) {
            convFileName.textContent = '📄 ' + convFileInput.files[0].name;
        }
    });

    // ── Range Slider Values ──
    rangeInputs.forEach(function (input) {
        const valueEl = document.getElementById(input.id + '-value');
        if (valueEl) {
            function updateValue() {
                valueEl.textContent = parseFloat(input.value).toFixed(1) + 'x';
            }
            input.addEventListener('input', updateValue);
            updateValue();
        }
    });

    // ── Tabs ──
    tabs.forEach(function (tab) {
        tab.addEventListener('click', function () {
            const target = tab.dataset.tab;

            // Update active tab
            tabs.forEach(function (t) { t.classList.remove('active'); });
            tab.classList.add('active');

            // Update active content
            document.querySelectorAll('.tab-content').forEach(function (c) {
                c.classList.remove('active');
            });
            document.getElementById('tab-' + target).classList.add('active');
        });
    });

    // ── Form Submission ──
    form.addEventListener('submit', function (e) {
        e.preventDefault();

        // Disable button
        btnGenerate.disabled = true;
        btnGenerate.innerHTML = '<span class="spinner"></span> <span>Enviando...</span>';

        const formData = new FormData(form);

        fetch('/render', {
            method: 'POST',
            body: formData,
        })
        .then(function (response) {
            return response.json();
        })
        .then(function (data) {
            if (data.error) {
                showToast(data.error, 'error');
                resetButton();
                return;
            }

            showToast('Renderização iniciada!', 'success');
            startProgressTracking(data.job_id);
            resetButton();
        })
        .catch(function (err) {
            showToast('Erro ao enviar: ' + err.message, 'error');
            resetButton();
        });
    });

    function resetButton() {
        btnGenerate.disabled = false;
        btnGenerate.innerHTML = '<span class="btn-icon">🎬</span> <span class="btn-text">Gerar Vídeo</span>';
    }

    // ── Progress Tracking via SSE ──
    function startProgressTracking(jobId) {
        progressSection.style.display = 'block';

        // Create progress item
        const item = document.createElement('div');
        item.className = 'progress-item';
        item.id = 'progress-' + jobId;
        item.innerHTML = `
            <div class="progress-header">
                <span class="progress-title">Job #${jobId}</span>
                <span class="progress-percent" id="percent-${jobId}">0%</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="bar-${jobId}" style="width: 0%"></div>
            </div>
            <div class="progress-detail" id="detail-${jobId}">Aguardando...</div>
        `;

        // Add at the top
        if (progressContainer.firstChild) {
            progressContainer.insertBefore(item, progressContainer.firstChild);
        } else {
            progressContainer.appendChild(item);
        }

        // Scroll to progress
        progressSection.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Start SSE
        const evtSource = new EventSource('/api/jobs/' + jobId + '/stream');

        evtSource.onmessage = function (event) {
            const data = JSON.parse(event.data);
            updateProgress(jobId, data);

            if (data.status === 'done' || data.status === 'error') {
                evtSource.close();
                refreshJobsList();
            }
        };

        evtSource.onerror = function () {
            evtSource.close();
            // Fallback: poll
            pollProgress(jobId);
        };
    }

    function updateProgress(jobId, data) {
        const percent = document.getElementById('percent-' + jobId);
        const bar = document.getElementById('bar-' + jobId);
        const detail = document.getElementById('detail-' + jobId);
        const item = document.getElementById('progress-' + jobId);

        if (!item) return;

        const progress = Math.round(data.progress || 0);

        if (percent) percent.textContent = progress + '%';
        if (bar) bar.style.width = progress + '%';
        if (detail) detail.textContent = data.detail || '';

        // Handle done
        if (data.status === 'done') {
            if (bar) {
                bar.style.background = 'linear-gradient(90deg, #25d366, #1eba56)';
                bar.style.animation = 'none';
            }
            if (percent) percent.textContent = '100% ✅';

            // Add download button
            const doneDiv = document.createElement('div');
            doneDiv.className = 'progress-done';
            doneDiv.innerHTML = `
                <a href="/api/download/${jobId}" class="btn btn-download">⬇️ Baixar Vídeo</a>
            `;
            item.appendChild(doneDiv);

            showToast('Vídeo pronto! Clique para baixar.', 'success', 8000);
        }

        // Handle error
        if (data.status === 'error' && data.error) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'progress-error';
            errorDiv.textContent = '❌ ' + data.error;
            item.appendChild(errorDiv);

            if (bar) {
                bar.style.background = '#ef4444';
                bar.style.animation = 'none';
            }
            if (percent) percent.textContent = '❌ Erro';

            showToast('Erro na renderização: ' + data.error, 'error', 10000);
        }
    }

    // Fallback polling if SSE fails
    function pollProgress(jobId) {
        const interval = setInterval(function () {
            fetch('/api/jobs/' + jobId)
                .then(function (r) { return r.json(); })
                .then(function (data) {
                    updateProgress(jobId, data);
                    if (data.status === 'done' || data.status === 'error') {
                        clearInterval(interval);
                        refreshJobsList();
                    }
                })
                .catch(function () {
                    clearInterval(interval);
                });
        }, 1000);
    }

    // ── Refresh Jobs List ──
    function refreshJobsList() {
        fetch('/api/jobs')
            .then(function (r) { return r.json(); })
            .then(function (jobs) {
                if (!jobs || jobs.length === 0) {
                    jobsList.innerHTML = '<div class="jobs-empty"><span class="empty-icon">🎞️</span><p>Nenhum vídeo gerado ainda</p></div>';
                    return;
                }

                jobsList.innerHTML = jobs.map(function (job) {
                    const downloadBtn = job.status === 'done'
                        ? `<a href="/api/download/${job.job_id}" class="btn btn-download">⬇️ Baixar</a>`
                        : '';

                    return `
                        <div class="job-item ${job.status}" data-job-id="${job.job_id}">
                            <div class="job-info">
                                <span class="job-name">Vídeo</span>
                                <span class="job-id">#${job.job_id}</span>
                                <span class="job-status-badge ${job.status}">${job.status}</span>
                            </div>
                            <div class="job-detail">${job.detail || ''}</div>
                            <div class="job-actions">
                                ${downloadBtn}
                                <button class="btn btn-delete" onclick="deleteJob('${job.job_id}')">🗑️</button>
                            </div>
                        </div>
                    `;
                }).join('');
            })
            .catch(function () {});
    }

    // ── Delete Job ──
    window.deleteJob = function (jobId) {
        if (!confirm('Remover este job e o vídeo gerado?')) return;

        fetch('/api/jobs/' + jobId, { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function () {
                showToast('Job removido.', 'info');
                refreshJobsList();

                // Remove progress item if exists
                const progressItem = document.getElementById('progress-' + jobId);
                if (progressItem) progressItem.remove();
            })
            .catch(function (err) {
                showToast('Erro ao remover: ' + err.message, 'error');
            });
    };

    // ── Initial load ──
    // Auto-resume tracking for in-progress jobs
    document.querySelectorAll('.job-item.rendering, .job-item.composing, .job-item.preparing, .job-item.queued, .job-item.parsing').forEach(function (el) {
        const jobId = el.dataset.jobId;
        if (jobId) {
            startProgressTracking(jobId);
        }
    });

})();
