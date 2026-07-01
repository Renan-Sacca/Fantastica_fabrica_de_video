// Tela de geração de áudio (OmniVoice) integrada ao site.
(function () {
    let voicesData = { custom: [] };
    let mode = "clone";
    const $ = (id) => document.getElementById(id);

    function toast(msg, type) {
        const container = document.getElementById("toast-container");
        if (!container) { alert(msg); return; }
        const el = document.createElement("div");
        el.className = "toast " + (type || "");
        el.textContent = msg;
        el.style.cssText = "background:#1c2330;border:1px solid rgba(255,255,255,.12);border-left:4px solid " +
            (type === "error" ? "#f85149" : type === "success" ? "#2ea043" : "#0e9488") +
            ";padding:12px 16px;border-radius:10px;margin-top:8px;color:#e6edf3;max-width:340px;";
        container.appendChild(el);
        setTimeout(() => el.remove(), 3800);
    }

    // ── Abas de modo ──
    document.querySelectorAll(".tab").forEach((t) => {
        t.addEventListener("click", () => {
            mode = t.dataset.mode;
            document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
            document.querySelectorAll(".panel").forEach((p) =>
                p.classList.toggle("active", p.dataset.panel === mode));
        });
    });

    // ── Símbolos não-verbais ──
    $("symbols").querySelectorAll(".symbol").forEach((s) => {
        s.addEventListener("click", () => {
            const ta = $("text");
            const tag = s.dataset.tag + " ";
            const start = ta.selectionStart || ta.value.length;
            ta.value = ta.value.slice(0, start) + tag + ta.value.slice(start);
            ta.focus();
        });
    });

    // ── Voice Design: monta o instruct ──
    function buildInstruct() {
        const free = $("d-free").value.trim();
        if (free) return free;
        const parts = ["d-gender", "d-age", "d-pitch", "d-style", "d-accent", "d-dialect"]
            .map((id) => $(id).value.trim())
            .filter(Boolean);
        return parts.join(", ");
    }
    function refreshPreview() {
        const instruct = buildInstruct();
        $("d-preview").textContent = "instruct: " + (instruct || "(vazio)");
    }
    ["d-gender", "d-age", "d-pitch", "d-style", "d-accent", "d-dialect", "d-free"].forEach((id) =>
        $(id).addEventListener("input", refreshPreview));
    refreshPreview();

    // ── Vozes ──
    async function loadVoices() {
        try {
            const res = await fetch("/audio3/api/voices");
            if (!res.ok) throw new Error("Falha ao carregar vozes");
            voicesData = await res.json();
            renderVoiceSelect();
            renderVoicesList();
        } catch (e) { toast(e.message, "error"); }
    }

    function renderVoiceSelect() {
        if (voicesData.custom.length) {
            $("voice").innerHTML = voicesData.custom
                .map((v) => `<option value="${v.id}">${v.name}</option>`).join("");
        } else {
            $("voice").innerHTML = `<option value="">Crie uma voz primeiro →</option>`;
        }
    }

    function renderVoicesList() {
        const cBox = $("custom-voices");
        if (voicesData.custom.length) {
            cBox.innerHTML = voicesData.custom
                .map((v) => `<span class="chip">${v.name}<span class="del" data-id="${v.id}" title="Remover">✕</span></span>`)
                .join("");
            cBox.querySelectorAll(".del").forEach((el) =>
                el.addEventListener("click", () => deleteVoice(el.dataset.id)));
        } else {
            cBox.innerHTML = `<p class="muted">Nenhuma ainda.</p>`;
        }
    }

    $("voice-form").addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = $("voice-name").value.trim();
        const file = $("voice-file").files[0];
        const refText = $("voice-reftext").value.trim();
        if (!name) return toast("Informe um nome para a voz.", "error");
        if (!file) return toast("Envie um áudio de referência.", "error");

        const fd = new FormData();
        fd.append("name", name);
        fd.append("reference_text", refText);
        fd.append("reference_audio", file);
        try {
            const res = await fetch("/audio3/api/voices", { method: "POST", body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Erro");
            toast("Voz criada!", "success");
            $("voice-name").value = ""; $("voice-file").value = ""; $("voice-reftext").value = "";
            await loadVoices();
        } catch (err) { toast(err.message, "error"); }
    });

    async function deleteVoice(id) {
        if (!confirm("Remover esta voz?")) return;
        try {
            const res = await fetch(`/audio3/api/voices/${id}`, { method: "DELETE" });
            if (!res.ok) throw new Error("Erro ao remover");
            toast("Voz removida.", "success");
            await loadVoices();
        } catch (err) { toast(err.message, "error"); }
    }

    // ── Gerar ──
    function numVal(id) {
        const v = $(id).value.trim();
        return v === "" ? "" : v;
    }

    $("gen-btn").addEventListener("click", async () => {
        const text = $("text").value.trim();
        if (!text) return toast("Digite um texto.", "error");

        const fd = new FormData();
        fd.append("text", text);
        fd.append("title", ($("title").value || "").trim());
        fd.append("mode", mode);

        if (mode === "clone") {
            const voice = $("voice").value;
            if (!voice) return toast("Crie/selecione uma voz de referência.", "error");
            fd.append("voice", voice);
        } else if (mode === "design") {
            const instruct = buildInstruct();
            if (!instruct) return toast("Defina ao menos um atributo de voz.", "error");
            fd.append("instruct", instruct);
        }

        // Parâmetros avançados
        [
            "num_step", "guidance_scale", "t_shift", "position_temperature",
            "class_temperature", "layer_penalty_factor", "speed", "duration",
            "audio_chunk_duration", "audio_chunk_threshold", "language_id",
        ].forEach((k) => fd.append(k, numVal("p-" + k)));

        fd.append("denoise", $("p-denoise").checked ? "true" : "false");
        fd.append("preprocess_prompt", $("p-preprocess_prompt").checked ? "true" : "false");
        fd.append("postprocess_output", $("p-postprocess_output").checked ? "true" : "false");

        const btn = $("gen-btn");
        btn.disabled = true;
        $("result-box").classList.add("hidden");
        showProgress(5, "Enviando para a fila...");

        try {
            const res = await fetch("/audio3/api/generate", { method: "POST", body: fd });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || "Erro");
            listenProgress(data.job_id, btn);
        } catch (err) {
            toast(err.message, "error");
            hideProgress();
            btn.disabled = false;
        }
    });

    function showProgress(pct, detail) {
        $("progress-box").classList.remove("hidden");
        $("progress-fill").style.width = pct + "%";
        $("progress-detail").textContent = detail || "";
    }
    function hideProgress() { $("progress-box").classList.add("hidden"); }

    function listenProgress(jobId, btn) {
        const es = new EventSource(`/audio3/api/progress/${jobId}/stream`);
        es.onmessage = (ev) => {
            let data;
            try { data = JSON.parse(ev.data); } catch { return; }
            showProgress(data.progress || 0, data.detail || "");
            if (data.status === "done") {
                es.close(); btn.disabled = false;
                showResult(`/audio3-files/${jobId}.wav`);
                toast("Áudio gerado!", "success");
            } else if (data.status === "error") {
                es.close(); btn.disabled = false; hideProgress();
                toast(data.detail || "Erro ao gerar áudio.", "error");
            }
        };
        es.onerror = () => { es.close(); btn.disabled = false; };
    }

    function showResult(url) {
        $("result-audio").src = url + "?t=" + Date.now();
        $("download-link").href = url;
        $("result-box").classList.remove("hidden");
        $("progress-fill").style.width = "100%";
        $("progress-detail").textContent = "Concluído.";
    }

    $("refresh-voices").addEventListener("click", loadVoices);
    loadVoices();
})();
