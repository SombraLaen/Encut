const state = {
    files: [],
    jobId: null,
    pollInterval: null,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function log(msg, tag = '') {
    const el = $('#log');
    const line = document.createElement('div');
    line.textContent = msg;
    if (tag) line.className = tag;
    el.appendChild(line);
    el.scrollTop = el.scrollHeight;
}

function setStatus(text) {
    $('#status').textContent = text;
}

function setProgress(pct, label = '') {
    $('#progress-fill').style.width = pct + '%';
    $('#progress-label').textContent = label;
}

function getSelectedMode() {
    return document.querySelector('input[name="mode"]:checked').value;
}

function getSelectedDetection() {
    return document.querySelector('input[name="detection"]:checked').value;
}

async function api(path, options = {}) {
    const resp = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    return resp.json();
}

async function loadStatus() {
    try {
        const data = await api('/api/status');
        $('#version').textContent = `v${data.version}`;
    } catch (e) {
        setStatus('Erro ao conectar com o servidor.');
    }
}

async function loadPresets() {
    try {
        const presets = await api('/api/presets');
        const select = $('#preset-select');
        select.innerHTML = '';
        for (const name of Object.keys(presets)) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            select.appendChild(opt);
        }
    } catch (e) {
        log('Erro ao carregar presets: ' + e, 'error');
    }
}

function addFiles(fileList) {
    for (const file of fileList) {
        if (!state.files.find(f => f.name === file.name && f.size === file.size)) {
            state.files.push(file);
        }
    }
    renderFileList();
    updateOutput();
}

function renderFileList() {
    const list = $('#file-list');
    list.innerHTML = '';
    state.files.forEach((file, i) => {
        const li = document.createElement('li');
        const size = formatBytes(file.size);
        li.innerHTML = `
            <span>${file.name} <span class="file-info">${size}</span></span>
            <span class="remove" data-index="${i}">&times;</span>
        `;
        list.appendChild(li);
    });
    $$('.remove').forEach(el => {
        el.addEventListener('click', (e) => {
            const idx = parseInt(e.target.dataset.index);
            state.files.splice(idx, 1);
            renderFileList();
            updateOutput();
        });
    });
}

function updateOutput() {
    const outEl = $('#output-path');
    if (state.files.length === 1) {
        const f = state.files[0];
        const stem = f.name.replace(/\.[^.]+$/, '');
        outEl.value = `${stem}_sem_silencio.mp4`;
    } else if (state.files.length > 1) {
        outEl.value = 'pasta_sem_silencio/';
    }
}

function formatBytes(bytes) {
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes.toFixed(1)} ${units[i]}`;
}

async function startProcessing() {
    if (state.files.length === 0) {
        log('Selecione pelo menos um vídeo.', 'warning');
        return;
    }

    const output = $('#output-path').value.trim();
    if (!output) {
        log('Defina o caminho de saída.', 'warning');
        return;
    }

    const body = {
        inputs: state.files.map(f => f.name),
        output: output,
        threshold_db: parseFloat($('#threshold').value),
        min_silence: parseFloat($('#min-silence').value),
        padding: parseFloat($('#padding').value),
        min_keep: 0.18,
        detection_mode: getSelectedDetection(),
        mode: getSelectedMode(),
        ignore_ranges: '',
        video_use_transcript: '',
    };

    $('#start-btn').disabled = true;
    $('#cancel-btn').disabled = false;
    setProgress(0, 'Iniciando...');
    log('Iniciando processamento...', 'info');

    try {
        const result = await api('/api/start', {
            method: 'POST',
            body: JSON.stringify(body),
        });
        state.jobId = result.job_id;
        startPolling();
    } catch (e) {
        log('Erro ao iniciar: ' + e, 'error');
        $('#start-btn').disabled = false;
        $('#cancel-btn').disabled = true;
    }
}

function startPolling() {
    if (state.pollInterval) clearInterval(state.pollInterval);
    state.pollInterval = setInterval(pollJob, 500);
}

async function pollJob() {
    if (!state.jobId) return;
    try {
        const job = await api(`/api/job/${state.jobId}`);
        if (job.log) {
            $('#log').innerHTML = '';
            for (const line of job.log) {
                let tag = '';
                if (line.startsWith('ERRO') || line.includes('falhou')) tag = 'error';
                else if (line.startsWith('Concluido') || line.startsWith('Pronto')) tag = 'success';
                else if (line.startsWith('Atualizacao')) tag = 'info';
                log(line, tag);
            }
        }
        if (job.progress !== undefined) {
            setProgress(job.progress);
        }
        if (job.status === 'done' || job.status === 'error') {
            clearInterval(state.pollInterval);
            state.pollInterval = null;
            $('#start-btn').disabled = false;
            $('#cancel-btn').disabled = true;
            if (job.status === 'done') {
                setProgress(100, 'Concluído');
                setStatus('Concluído.');
                log('Processamento concluído com sucesso!', 'success');
            } else {
                setProgress(0, 'Erro');
                setStatus('Erro no processamento.');
                log('Erro: ' + (job.error || 'desconhecido'), 'error');
            }
        }
    } catch (e) {
        log('Erro ao verificar status: ' + e, 'error');
    }
}

async function cancelJob() {
    if (!state.jobId) return;
    await api(`/api/cancel/${state.jobId}`, { method: 'POST' });
    log('Cancelamento solicitado.', 'warning');
}

function clearLog() {
    $('#log').innerHTML = '';
}

async function loadPreset() {
    const name = $('#preset-select').value;
    if (!name) return;
    const presets = await api('/api/presets');
    const preset = presets[name];
    if (!preset) return;
    $('#threshold').value = preset.threshold_db;
    $('#min-silence').value = preset.min_silence;
    $('#padding').value = preset.padding;
    $(`input[name="detection"][value="${preset.detection_mode}"]`).checked = true;
    $(`input[name="mode"][value="${preset.mode}"]`).checked = true;
    log(`Preset carregado: ${name}`, 'info');
}

// Event listeners
$('#pick-files').addEventListener('click', () => $('#file-input').click());
$('#file-input').addEventListener('change', (e) => addFiles(e.target.files));
$('#clear-files').addEventListener('click', () => {
    state.files = [];
    renderFileList();
    $('#output-path').value = '';
});
$('#start-btn').addEventListener('click', startProcessing);
$('#cancel-btn').addEventListener('click', cancelJob);
$('#clear-log').addEventListener('click', clearLog);
$('#load-preset').addEventListener('click', loadPreset);

// Init
loadStatus();
loadPresets();
