/**
 * LLM Benchmark Management Dashboard - Frontend Logic (Vanilla ES6)
 * Phase 6 Web Interface: Heatmap Matrix, Diff Inspector, Question CRUD & Live Sandbox
 */

// Application State
const state = {
    activeView: 'matrix-view',
    matrixData: null,
    questions: [],
    models: [],
    suites: [],
    filters: {
        search: '',
        tier: 'all',
        category: 'all',
        status: 'all'
    },
    diffSelectedModels: new Set(['llama3.2', 'qwen2.5-coder:3b', 'gemini-3.1-flash-lite']),
    currentEditingQId: null,
    isNewQuestion: false
};

// ==============================================================================
// Initialization & Lifecycle
// ==============================================================================

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initHealthMonitoring();
    initMatrixEvents();
    initDiffEvents();
    initCrudEvents();
    initSandboxEvents();
    initDrawer();

    // Initial data fetch
    fetchHealth();
    fetchMatrix();
    fetchQuestions();
});

// ==============================================================================
// Navigation & Health Monitoring
// ==============================================================================

function initNavigation() {
    const tabs = document.querySelectorAll('.nav-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            const viewId = tab.dataset.view;
            state.activeView = viewId;

            document.querySelectorAll('.view-panel').forEach(panel => {
                panel.classList.remove('active');
            });

            const activePanel = document.getElementById(viewId);
            if (activePanel) {
                activePanel.classList.add('active');
            }

            // Lazy load or refresh view-specific data
            if (viewId === 'diff-view' && !document.getElementById('diff-question-select').value) {
                populateDiffDropdowns();
            } else if (viewId === 'crud-view') {
                renderCrudSidebar();
            } else if (viewId === 'sandbox-view') {
                populateSandboxPresets();
            }
        });
    });
}

function initHealthMonitoring() {
    // Poll health every 30 seconds
    setInterval(fetchHealth, 30000);
}

async function fetchHealth() {
    try {
        const res = await fetch('/api/health');
        if (!res.ok) return;
        const data = await res.json();

        // Update Ollama dot
        const ollamaDot = document.getElementById('ollama-dot');
        const ollamaText = document.getElementById('ollama-status-text');
        if (data.ollama_connected) {
            ollamaDot.className = 'status-dot active';
            ollamaText.textContent = `${data.ollama_models?.length || 0} Models`;
            updateOllamaModelsList(data.ollama_models || []);
        } else {
            ollamaDot.className = 'status-dot';
            ollamaText.textContent = 'Offline';
        }

        // Update Gemini dot
        const geminiDot = document.getElementById('gemini-dot');
        const geminiText = document.getElementById('gemini-status-text');
        if (data.gemini_configured) {
            geminiDot.className = 'status-dot active';
            geminiText.textContent = 'Ready';
        } else {
            geminiDot.className = 'status-dot';
            geminiText.textContent = 'No Key';
        }

        // Update DB stats
        const dbDot = document.getElementById('db-dot');
        const dbText = document.getElementById('db-status-text');
        if (data.db_connected) {
            dbDot.className = 'status-dot active';
            const runs = data.stats?.benchmark_runs || 0;
            dbText.textContent = `${runs} Runs`;
        }
    } catch (e) {
        console.warn('Health check error:', e);
    }
}

function updateOllamaModelsList(models) {
    if (!models.length) return;
    const optgroup = document.getElementById('optgroup-ollama');
    if (optgroup) {
        optgroup.innerHTML = '';
        models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m;
            opt.textContent = m;
            optgroup.appendChild(opt);
        });
    }
}

// ==============================================================================
// Heatmap Matrix Explorer
// ==============================================================================

function initMatrixEvents() {
    document.getElementById('matrix-search').addEventListener('input', e => {
        state.filters.search = e.target.value.toLowerCase().trim();
        renderMatrix();
    });

    document.querySelectorAll('#tier-pills .pill-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#tier-pills .pill-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            state.filters.tier = btn.dataset.tier;
            renderMatrix();
        });
    });

    document.getElementById('category-filter').addEventListener('change', e => {
        state.filters.category = e.target.value;
        renderMatrix();
    });

    document.getElementById('status-filter').addEventListener('change', e => {
        state.filters.status = e.target.value;
        renderMatrix();
    });

    document.getElementById('btn-refresh-matrix').addEventListener('click', () => {
        fetchMatrix();
        showToast('Refreshing matrix data...');
    });
}

async function fetchMatrix() {
    try {
        const res = await fetch('/api/matrix');
        if (!res.ok) throw new Error('Failed to load matrix');
        state.matrixData = await res.json();
        updateSummaryCards();
        populateCategoryFilter();
        renderMatrix();
    } catch (e) {
        console.error('Matrix load error:', e);
        document.getElementById('matrix-body').innerHTML = `
            <tr><td colspan="10" class="error-cell">Failed to load matrix data: ${e.message}</td></tr>
        `;
    }
}

function updateSummaryCards() {
    if (!state.matrixData) return;
    const { models, questions } = state.matrixData;

    document.getElementById('stat-total-questions').textContent = questions.length;
    document.getElementById('stat-total-models').textContent = models.length;

    if (models.length > 0) {
        const top = models[0];
        document.getElementById('stat-top-model').textContent = top.model_name;
        document.getElementById('stat-top-acc').textContent = `${top.pass_rate_pct}% Accuracy (${top.questions_solved}/${top.total_questions})`;

        // Calculate average speed
        const speeds = models.map(m => m.avg_speed_tps).filter(s => s > 0);
        const avg = speeds.length ? (speeds.reduce((a, b) => a + b, 0) / speeds.length).toFixed(1) : '--';
        document.getElementById('stat-avg-speed').textContent = `${avg} tok/s`;
    }
}

function populateCategoryFilter() {
    if (!state.matrixData) return;
    const catSelect = document.getElementById('category-filter');
    const categories = new Set(state.matrixData.questions.map(q => q.category).filter(Boolean));

    catSelect.innerHTML = '<option value="all">All Categories</option>';
    Array.from(categories).sort().forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        catSelect.appendChild(opt);
    });
}

function renderMatrix() {
    if (!state.matrixData) return;
    const { models, questions, matrix } = state.matrixData;

    // Render Headers
    const headerRow = document.getElementById('matrix-header-row');
    headerRow.innerHTML = `
        <th class="col-probe-id sticky-col">Question ID &amp; Prompt</th>
        <th class="col-tier">Tier</th>
        <th class="col-category">Category</th>
    `;

    models.forEach(m => {
        const th = document.createElement('th');
        th.className = 'model-header-cell';
        const accClass = m.pass_rate_pct >= 85 ? 'model-acc-high' : (m.pass_rate_pct >= 70 ? 'model-acc-med' : 'model-acc-low');
        th.innerHTML = `
            <span class="model-header-name">${escapeHtml(m.model_name)}</span>
            <div class="model-header-stats">
                <span class="model-acc-badge ${accClass}">${m.pass_rate_pct}%</span>
                <span>${m.avg_speed_tps || '--'} tok/s</span>
            </div>
        `;
        headerRow.appendChild(th);
    });

    // Filter Questions
    const filteredQuestions = questions.filter(q => {
        // Search filter
        if (state.filters.search) {
            const term = state.filters.search;
            const matchId = q.test_id.toLowerCase().includes(term);
            const matchText = (q.question_text || '').toLowerCase().includes(term);
            if (!matchId && !matchText) return false;
        }

        // Tier filter
        if (state.filters.tier !== 'all' && String(q.tier) !== String(state.filters.tier)) {
            return false;
        }

        // Category filter
        if (state.filters.category !== 'all' && q.category !== state.filters.category) {
            return false;
        }

        // Status filter
        if (state.filters.status !== 'all') {
            const qRes = matrix[q.test_id] || {};
            const testedModels = models.filter(m => qRes[m.model_name]);
            if (!testedModels.length) return false;

            const passCount = testedModels.filter(m => qRes[m.model_name].passed).length;
            if (state.filters.status === 'pass' && passCount !== testedModels.length) return false;
            if (state.filters.status === 'fail' && passCount !== 0) return false;
            if (state.filters.status === 'split' && (passCount === 0 || passCount === testedModels.length)) return false;
        }

        return true;
    });

    // Render Body
    const tbody = document.getElementById('matrix-body');
    if (!filteredQuestions.length) {
        tbody.innerHTML = `<tr><td colspan="${models.length + 3}" class="empty-cell">No questions match the selected filters.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';
    filteredQuestions.forEach(q => {
        const tr = document.createElement('tr');

        // Sticky Probe Info
        const tdProbe = document.createElement('td');
        tdProbe.className = 'col-probe-id sticky-col';
        tdProbe.innerHTML = `
            <div class="probe-cell-content">
                <span class="probe-title">${escapeHtml(q.test_id)}</span>
                <span class="probe-prompt-preview">${escapeHtml(q.question_text || '')}</span>
            </div>
        `;
        tr.appendChild(tdProbe);

        // Tier Badge
        const tdTier = document.createElement('td');
        tdTier.className = 'col-tier';
        tdTier.innerHTML = `<span class="badge tier-${q.tier}">T${q.tier}</span>`;
        tr.appendChild(tdTier);

        // Category Badge
        const tdCat = document.createElement('td');
        tdCat.className = 'col-category';
        tdCat.innerHTML = `<span class="badge secondary">${escapeHtml(q.category || 'general')}</span>`;
        tr.appendChild(tdCat);

        // Model Cells
        const qResults = matrix[q.test_id] || {};
        models.forEach(m => {
            const tdCell = document.createElement('td');
            tdCell.className = 'matrix-cell';
            const res = qResults[m.model_name];

            if (res) {
                const passClass = res.passed ? 'pass' : 'fail';
                const passText = res.passed ? 'PASS' : 'FAIL';
                const detailText = res.passed ? `${res.speed_tps} t/s` : `${res.latency_sec}s`;
                tdCell.innerHTML = `
                    <div class="result-pill ${passClass}" data-result-id="${res.result_id}">
                        <span>${passText}</span>
                        <span style="opacity: 0.7; font-size: 0.68rem;">${detailText}</span>
                    </div>
                `;
                tdCell.addEventListener('click', () => openResultDrawer(res.result_id));
            } else {
                tdCell.innerHTML = `<span class="result-pill untested">-</span>`;
            }

            tr.appendChild(tdCell);
        });

        tbody.appendChild(tr);
    });
}

// ==============================================================================
// Result Drawer (Cell Inspection)
// ==============================================================================

function initDrawer() {
    const overlay = document.getElementById('drawer-overlay');
    const drawer = document.getElementById('result-drawer');
    const closeBtn = document.getElementById('btn-close-drawer');

    const close = () => {
        drawer.classList.remove('open');
        overlay.classList.remove('open');
    };

    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', close);
}

async function openResultDrawer(resultId) {
    const drawer = document.getElementById('result-drawer');
    const overlay = document.getElementById('drawer-overlay');

    drawer.classList.add('open');
    overlay.classList.add('open');

    // Reset drawer state
    document.getElementById('drawer-title').textContent = 'Loading test details...';
    document.getElementById('drawer-output').textContent = 'Fetching completion...';
    document.getElementById('drawer-assertions-list').innerHTML = '';

    try {
        const res = await fetch(`/api/result/${resultId}`);
        if (!res.ok) throw new Error('Result not found');
        const data = await res.json();

        const badge = document.getElementById('drawer-status-badge');
        badge.className = `badge ${data.passed ? 'tier-1' : 'tier-4'}`;
        badge.textContent = data.passed ? 'PASSED' : 'FAILED';

        document.getElementById('drawer-title').textContent = `${data.model_name} on ${data.test_id}`;
        document.getElementById('drawer-model').textContent = data.model_name;
        document.getElementById('drawer-qid').textContent = data.test_id;
        document.getElementById('drawer-latency').textContent = `${data.latency_sec}s`;
        document.getElementById('drawer-speed').textContent = `${data.eval_tokens_per_sec} tok/s`;
        document.getElementById('drawer-tokens').textContent = `${data.prompt_tokens} prompt + ${data.completion_tokens} out`;
        document.getElementById('drawer-timestamp').textContent = data.timestamp || '--';
        document.getElementById('drawer-prompt').textContent = data.question_text || '--';
        document.getElementById('drawer-output').textContent = data.raw_output || '(Empty completion)';

        // Render assertions
        const assertContainer = document.getElementById('drawer-assertions-list');
        assertContainer.innerHTML = '';
        if (data.assertions && data.assertions.length) {
            data.assertions.forEach(a => {
                const item = document.createElement('div');
                item.className = `eval-item ${a.passed ? 'pass' : 'fail'}`;
                item.innerHTML = `
                    <span>${a.passed ? '✓' : '✗'}</span>
                    <span>${escapeHtml(a.message)}</span>
                `;
                assertContainer.appendChild(item);
            });
        } else {
            assertContainer.innerHTML = '<span class="text-muted">No assertion records found.</span>';
        }
    } catch (e) {
        document.getElementById('drawer-title').textContent = 'Error loading result';
        document.getElementById('drawer-output').textContent = e.message;
    }
}

// ==============================================================================
// Side-by-Side Diff Inspector
// ==============================================================================

function initDiffEvents() {
    document.getElementById('btn-load-diff').addEventListener('click', loadDiffInspector);
    document.getElementById('diff-question-select').addEventListener('change', loadDiffInspector);
}

function populateDiffDropdowns() {
    if (!state.matrixData) return;
    const qSelect = document.getElementById('diff-question-select');
    const prevVal = qSelect.value;
    qSelect.innerHTML = '<option value="">-- Choose Question --</option>';

    state.matrixData.questions.forEach(q => {
        const opt = document.createElement('option');
        opt.value = q.test_id;
        opt.textContent = `[T${q.tier}] ${q.test_id} - ${q.question_text.slice(0, 50)}...`;
        qSelect.appendChild(opt);
    });

    if (prevVal) qSelect.value = prevVal;

    // Checkboxes for models
    const cbContainer = document.getElementById('diff-model-checkboxes');
    cbContainer.innerHTML = '';
    state.matrixData.models.forEach(m => {
        const label = document.createElement('label');
        const isSelected = state.diffSelectedModels.has(m.model_name);
        label.className = `checkbox-pill ${isSelected ? 'selected' : ''}`;
        label.innerHTML = `
            <input type="checkbox" value="${escapeHtml(m.model_name)}" ${isSelected ? 'checked' : ''} style="display:none;">
            <span>${escapeHtml(m.model_name)}</span>
        `;
        label.addEventListener('click', (e) => {
            const cb = label.querySelector('input');
            cb.checked = !cb.checked;
            if (cb.checked) {
                state.diffSelectedModels.add(m.model_name);
                label.classList.add('selected');
            } else {
                state.diffSelectedModels.delete(m.model_name);
                label.classList.remove('selected');
            }
        });
        cbContainer.appendChild(label);
    });
}

async function loadDiffInspector() {
    const qid = document.getElementById('diff-question-select').value;
    if (!qid) return;

    const modelsParam = Array.from(state.diffSelectedModels).join(',');
    const container = document.getElementById('diff-columns-grid');
    const promptCard = document.getElementById('diff-prompt-card');

    container.innerHTML = '<div class="empty-state">Loading side-by-side completions...</div>';

    try {
        const res = await fetch(`/api/diff?question_id=${encodeURIComponent(qid)}&models=${encodeURIComponent(modelsParam)}`);
        if (!res.ok) throw new Error('Failed to fetch diff');
        const data = await res.json();

        // Show prompt card
        promptCard.style.display = 'block';
        document.getElementById('diff-meta-tier').textContent = `Tier ${data.question.tier}`;
        document.getElementById('diff-meta-tier').className = `badge tier-${data.question.tier}`;
        document.getElementById('diff-meta-cat').textContent = data.question.category || 'general';
        document.getElementById('diff-meta-suite').textContent = data.question.suite_name || 'Suite';
        document.getElementById('diff-meta-text').textContent = data.question.question_text;

        // Render columns
        container.innerHTML = '';
        if (!data.models || !data.models.length) {
            container.innerHTML = '<div class="empty-state">No model outputs recorded for this question with selected models.</div>';
            return;
        }

        data.models.forEach(m => {
            const col = document.createElement('div');
            col.className = 'diff-model-column';

            const passBadgeClass = m.passed ? 'pass' : 'fail';
            const passText = m.passed ? 'PASSED' : 'FAILED';

            let thinkHtml = '';
            if (m.think_content) {
                thinkHtml = `
                    <div class="diff-think-accordion">
                        <div class="diff-think-header" onclick="this.parentElement.classList.toggle('open')">
                            <span>🧠 Reasoning Trace (&lt;think&gt;)</span>
                            <span>▾</span>
                        </div>
                        <div class="diff-think-body">${escapeHtml(m.think_content)}</div>
                    </div>
                `;
            }

            let assertionsHtml = '';
            if (m.assertions && m.assertions.length) {
                assertionsHtml = `
                    <div class="diff-assertions-summary">
                        ${m.assertions.map(a => `
                            <div class="eval-item ${a.passed ? 'pass' : 'fail'}" style="margin-bottom:0.25rem;">
                                <span>${a.passed ? '✓' : '✗'}</span>
                                <span style="font-size:0.75rem;">${escapeHtml(a.message)}</span>
                            </div>
                        `).join('')}
                    </div>
                `;
            }

            col.innerHTML = `
                <div class="diff-column-header">
                    <span class="diff-column-title">${escapeHtml(m.model_name)}</span>
                    <span class="verdict-badge ${passBadgeClass}">${passText}</span>
                </div>
                <div class="diff-column-telemetry">
                    <span>Speed: <b>${m.eval_tokens_per_sec || '--'} tok/s</b></span>
                    <span>Latency: <b>${m.latency_sec || '--'}s</b></span>
                </div>
                ${thinkHtml}
                <div class="diff-completion-body">${escapeHtml(m.final_content || m.raw_output || '')}</div>
                ${assertionsHtml}
            `;
            container.appendChild(col);
        });
    } catch (e) {
        container.innerHTML = `<div class="empty-state error">Error loading diff: ${e.message}</div>`;
    }
}

// ==============================================================================
// Question CRUD Manager
// ==============================================================================

function initCrudEvents() {
    document.getElementById('btn-create-question-modal').addEventListener('click', prepareNewQuestion);
    document.getElementById('btn-add-assertion').addEventListener('click', () => addAssertionRow());
    document.getElementById('q-temperature').addEventListener('input', e => {
        document.getElementById('q-temp-val').textContent = e.target.value;
    });
    document.getElementById('crud-search').addEventListener('input', e => {
        renderCrudSidebar(e.target.value.toLowerCase().trim());
    });
    document.getElementById('btn-save-question').addEventListener('click', saveQuestion);
    document.getElementById('btn-delete-question').addEventListener('click', deleteQuestion);
}

async function fetchQuestions() {
    try {
        const res = await fetch('/api/questions');
        if (!res.ok) return;
        const data = await res.json();
        state.questions = data.questions || [];
        renderCrudSidebar();
    } catch (e) {
        console.error('Fetch questions error:', e);
    }
}

function renderCrudSidebar(filterTerm = '') {
    const list = document.getElementById('crud-questions-list');
    list.innerHTML = '';

    const filtered = state.questions.filter(q => {
        if (!filterTerm) return true;
        return q.test_id.toLowerCase().includes(filterTerm) ||
               (q.question_text || '').toLowerCase().includes(filterTerm) ||
               (q.category || '').toLowerCase().includes(filterTerm);
    });

    if (!filtered.length) {
        list.innerHTML = '<div style="padding:1rem;color:var(--text-muted);font-size:0.8rem;">No questions found.</div>';
        return;
    }

    filtered.forEach(q => {
        const item = document.createElement('div');
        const isActive = state.currentEditingQId === q.id;
        item.className = `crud-item ${isActive ? 'active' : ''}`;
        item.innerHTML = `
            <div class="crud-item-title">${escapeHtml(q.test_id)}</div>
            <div class="crud-item-meta">
                <span class="badge tier-${q.tier}">T${q.tier}</span>
                <span class="badge secondary">${escapeHtml(q.category)}</span>
            </div>
        `;
        item.addEventListener('click', () => loadQuestionIntoEditor(q));
        list.appendChild(item);
    });
}

function loadQuestionIntoEditor(q) {
    state.currentEditingQId = q.id;
    state.isNewQuestion = false;

    renderCrudSidebar(document.getElementById('crud-search').value.toLowerCase().trim());

    document.getElementById('editor-title').textContent = `Edit: ${q.test_id}`;
    document.getElementById('editor-status-badge').textContent = 'Saved';
    document.getElementById('editor-status-badge').className = 'badge secondary';
    document.getElementById('btn-delete-question').style.display = 'inline-flex';

    document.getElementById('q-edit-id').value = q.id;
    document.getElementById('q-test-id').value = q.test_id;
    document.getElementById('q-test-id').disabled = true; // Lock slug for existing questions
    document.getElementById('q-name').value = q.test_id;
    document.getElementById('q-suite-file').value = q.suite_file || 'questions_basic.xml';
    document.getElementById('q-tier').value = q.tier;
    document.getElementById('q-category').value = q.category || 'general';
    document.getElementById('q-difficulty').value = q.difficulty || 'medium';
    document.getElementById('q-prompt').value = q.question_text || '';
    document.getElementById('q-system-prompt').value = q.system_prompt || '';
    document.getElementById('q-temperature').value = q.temperature || 0.0;
    document.getElementById('q-temp-val').textContent = q.temperature || 0.0;
    document.getElementById('q-max-tokens').value = q.max_tokens || 1200;

    // Load assertions
    const container = document.getElementById('assertions-list-container');
    container.innerHTML = '';
    if (q.assertions && q.assertions.length) {
        q.assertions.forEach(a => addAssertionRow(a));
    }
}

function prepareNewQuestion() {
    state.currentEditingQId = null;
    state.isNewQuestion = true;

    document.getElementById('editor-title').textContent = 'Create New Question';
    document.getElementById('editor-status-badge').textContent = 'New Probe';
    document.getElementById('editor-status-badge').className = 'badge tier-1';
    document.getElementById('btn-delete-question').style.display = 'none';

    document.getElementById('q-edit-id').value = '';
    document.getElementById('q-test-id').value = '';
    document.getElementById('q-test-id').disabled = false;
    document.getElementById('q-name').value = '';
    document.getElementById('q-tier').value = '1';
    document.getElementById('q-category').value = 'custom';
    document.getElementById('q-difficulty').value = 'medium';
    document.getElementById('q-prompt').value = '';
    document.getElementById('q-system-prompt').value = '';
    document.getElementById('q-temperature').value = 0.0;
    document.getElementById('q-temp-val').textContent = '0.0';
    document.getElementById('q-max-tokens').value = 1200;

    const container = document.getElementById('assertions-list-container');
    container.innerHTML = '';
    addAssertionRow({ rule_type: 'contains', expected_values: [''], case_sensitive: false });
}

function addAssertionRow(data = null, targetContainerId = 'assertions-list-container') {
    const container = document.getElementById(targetContainerId);
    const row = document.createElement('div');
    row.className = 'assertion-row';

    const ruleTypes = [
        'contains', 'contains_any', 'not_contains', 'contains_all',
        'regex', 'exact', 'min_words', 'max_words', 'exact_words',
        'min_length', 'max_latency_sec', 'min_tokens_per_sec'
    ];

    const currentType = data?.rule_type || 'contains';
    const expVals = (data?.expected_values || ['']).join(', ');
    const isCs = Boolean(data?.case_sensitive);

    row.innerHTML = `
        <select class="styled-select assert-type">
            ${ruleTypes.map(t => `<option value="${t}" ${t === currentType ? 'selected' : ''}>${t}</option>`).join('')}
        </select>
        <input type="text" class="assert-val" placeholder="Expected value(s) separated by comma..." value="${escapeHtml(expVals)}">
        <label style="display:flex;align-items:center;gap:0.3rem;font-size:0.75rem;cursor:pointer;">
            <input type="checkbox" class="assert-cs" ${isCs ? 'checked' : ''}> Case Sensitive
        </label>
        <button type="button" class="btn-remove-assert" title="Remove Rule">&times;</button>
    `;

    row.querySelector('.btn-remove-assert').addEventListener('click', () => row.remove());
    container.appendChild(row);
}

async function saveQuestion() {
    const testId = document.getElementById('q-test-id').value.trim();
    const promptText = document.getElementById('q-prompt').value.trim();

    if (!testId || !promptText) {
        showToast('Test ID and Prompt are required!', 'error');
        return;
    }

    // Collect assertions
    const assertionRows = document.querySelectorAll('#assertions-list-container .assertion-row');
    const assertions = [];
    assertionRows.forEach(row => {
        const ruleType = row.querySelector('.assert-type').value;
        const rawVal = row.querySelector('.assert-val').value;
        const cs = row.querySelector('.assert-cs').checked;
        const vals = rawVal.split(',').map(s => s.trim()).filter(Boolean);
        assertions.push({
            rule_type: ruleType,
            expected_values: vals,
            case_sensitive: cs
        });
    });

    const payload = {
        test_id: testId,
        name: document.getElementById('q-name').value.trim() || testId,
        suite_file: document.getElementById('q-suite-file').value,
        tier: parseInt(document.getElementById('q-tier').value, 10),
        category: document.getElementById('q-category').value.trim(),
        difficulty: document.getElementById('q-difficulty').value,
        question_text: promptText,
        system_prompt: document.getElementById('q-system-prompt').value.trim(),
        temperature: parseFloat(document.getElementById('q-temperature').value),
        max_tokens: parseInt(document.getElementById('q-max-tokens').value, 10),
        assertions
    };

    try {
        let res;
        if (state.isNewQuestion) {
            res = await fetch('/api/question', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        } else {
            res = await fetch(`/api/question/${encodeURIComponent(testId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
        }

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to save question');

        showToast(`Question '${testId}' saved to DB and synced to XML!`);
        fetchQuestions();
        fetchMatrix();
    } catch (e) {
        showToast(`Save error: ${e.message}`, 'error');
    }
}

async function deleteQuestion() {
    const testId = document.getElementById('q-test-id').value.trim();
    if (!testId) return;

    if (!confirm(`Are you sure you want to delete / archive question '${testId}'?`)) {
        return;
    }

    try {
        const res = await fetch(`/api/question/${encodeURIComponent(testId)}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Failed to delete');

        showToast(`Question '${testId}' removed from active suite.`);
        prepareNewQuestion();
        fetchQuestions();
        fetchMatrix();
    } catch (e) {
        showToast(`Delete error: ${e.message}`, 'error');
    }
}

// ==============================================================================
// Live Sandbox Playground
// ==============================================================================

function initSandboxEvents() {
    document.getElementById('btn-sandbox-add-assertion').addEventListener('click', () => {
        addAssertionRow(null, 'sandbox-assertions-container');
    });

    document.getElementById('sandbox-temp').addEventListener('input', e => {
        document.getElementById('sandbox-temp-val').textContent = e.target.value;
    });

    document.getElementById('sandbox-preset').addEventListener('change', e => {
        const qid = e.target.value;
        if (!qid) return;
        const q = state.questions.find(item => item.test_id === qid);
        if (!q) return;

        document.getElementById('sandbox-prompt').value = q.question_text || '';
        document.getElementById('sandbox-system-prompt').value = q.system_prompt || '';
        document.getElementById('sandbox-temp').value = q.temperature || 0.0;
        document.getElementById('sandbox-temp-val').textContent = q.temperature || 0.0;

        const container = document.getElementById('sandbox-assertions-container');
        container.innerHTML = '';
        if (q.assertions && q.assertions.length) {
            q.assertions.forEach(a => addAssertionRow(a, 'sandbox-assertions-container'));
        }
    });

    // Radio button changes for inference model selection
    document.querySelectorAll('input[name="sandbox_model"]').forEach(radio => {
        radio.addEventListener('change', () => {
            document.querySelectorAll('#sandbox-model-radio-group .radio-pill').forEach(p => p.classList.remove('selected'));
            if (radio.checked) {
                radio.closest('.radio-pill')?.classList.add('selected');
            }
        });
    });

    document.getElementById('btn-run-sandbox').addEventListener('click', runSandboxProbe);
}

function setSandboxModel(modelName) {
    const radio = document.querySelector(`input[name="sandbox_model"][value="${modelName}"]`);
    if (radio) {
        radio.checked = true;
        document.querySelectorAll('#sandbox-model-radio-group .radio-pill').forEach(p => p.classList.remove('selected'));
        radio.closest('.radio-pill')?.classList.add('selected');
    }
}

function populateSandboxPresets() {
    const select = document.getElementById('sandbox-preset');
    select.innerHTML = '<option value="">-- Choose Existing Question --</option>';
    state.questions.forEach(q => {
        const opt = document.createElement('option');
        opt.value = q.test_id;
        opt.textContent = `[T${q.tier}] ${q.test_id} - ${q.question_text.slice(0, 50)}...`;
        select.appendChild(opt);
    });
}

let sandboxAbortController = null;

async function runSandboxProbe() {
    const checkedRadio = document.querySelector('input[name="sandbox_model"]:checked');
    const model = checkedRadio ? checkedRadio.value : (document.getElementById('sandbox-model')?.value || 'deepseek-r1:1.5b');
    const question = document.getElementById('sandbox-prompt').value.trim();
    const systemPrompt = document.getElementById('sandbox-system-prompt').value.trim();
    const temperature = parseFloat(document.getElementById('sandbox-temp').value);
    const maxTokens = parseInt(document.getElementById('sandbox-max-tok').value, 10);

    if (!question) {
        showToast('Please enter a question or prompt for the sandbox', 'error');
        return;
    }

    // Collect sandbox assertions
    const rows = document.querySelectorAll('#sandbox-assertions-container .assertion-row');
    const assertions = [];
    rows.forEach(r => {
        const ruleType = r.querySelector('.assert-type').value;
        const rawVal = r.querySelector('.assert-val').value;
        const cs = r.querySelector('.assert-cs').checked;
        const vals = rawVal.split(',').map(s => s.trim()).filter(Boolean);
        assertions.push({
            rule_type: ruleType,
            expected_values: vals,
            case_sensitive: cs
        });
    });

    const spinner = document.getElementById('sandbox-spinner');
    const btn = document.getElementById('btn-run-sandbox');
    const emptyState = document.getElementById('sandbox-empty');
    const content = document.getElementById('sandbox-output-content');
    const thinkSection = document.getElementById('sandbox-thinking-section');
    const thinkOutput = document.getElementById('sandbox-thinking-output');
    const thinkBadge = document.getElementById('sandbox-thinking-badge');
    const rawOutput = document.getElementById('sandbox-raw-output');
    const assertContainer = document.getElementById('sandbox-assertion-results-list');

    btn.disabled = true;
    spinner.style.display = 'inline-block';
    emptyState.style.display = 'none';
    content.style.display = 'block';

    // Reset UI fields
    thinkSection.style.display = 'none';
    thinkOutput.textContent = '';
    thinkBadge.textContent = 'Streaming...';
    rawOutput.textContent = '';
    assertContainer.innerHTML = '<span class="text-muted" style="font-size:0.8rem;">Evaluating assertions upon stream completion...</span>';

    document.getElementById('sandbox-verdict').textContent = 'STREAM';
    document.getElementById('sandbox-verdict').className = 'verdict-badge';
    document.getElementById('sandbox-verdict-text').textContent = `Streaming tokens live from ${model}...`;
    document.getElementById('chip-latency').textContent = 'Latency: --';
    document.getElementById('chip-speed').textContent = 'Speed: --';
    document.getElementById('chip-tokens').textContent = 'Tokens: --';

    sandboxAbortController = new AbortController();

    try {
        const res = await fetch('/api/sandbox/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            signal: sandboxAbortController.signal,
            body: JSON.stringify({
                model,
                question,
                system_prompt: systemPrompt,
                temperature,
                max_tokens: maxTokens,
                assertions
            })
        });

        if (!res.ok) {
            const errJson = await res.json().catch(() => ({}));
            throw new Error(errJson.error || `HTTP ${res.status} error from server`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        let streamFinished = false;
        while (!streamFinished) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // keep partial line in buffer

            for (const line of lines) {
                const trimmed = line.trim();
                if (!trimmed.startsWith('data:')) continue;

                const jsonStr = trimmed.slice(5).trim();
                if (!jsonStr) continue;

                let eventData;
                try {
                    eventData = JSON.parse(jsonStr);
                } catch {
                    continue;
                }

                if (eventData.type === 'token') {
                    if (eventData.channel === 'thinking') {
                        if (thinkSection.style.display === 'none') {
                            thinkSection.style.display = 'block';
                        }
                        thinkOutput.textContent += eventData.text;
                        thinkOutput.scrollTop = thinkOutput.scrollHeight;
                    } else if (eventData.channel === 'content') {
                        if (thinkBadge.textContent !== 'Completed') {
                            thinkBadge.textContent = 'Completed';
                            thinkBadge.style.color = 'var(--emerald-400)';
                            thinkBadge.style.borderColor = 'rgba(52, 211, 153, 0.3)';
                        }
                        rawOutput.textContent += eventData.text;
                    }
                } else if (eventData.type === 'done') {
                    streamFinished = true;
                    const badge = document.getElementById('sandbox-verdict');
                    const text = document.getElementById('sandbox-verdict-text');

                    if (eventData.all_passed) {
                        badge.textContent = 'PASS';
                        badge.className = 'verdict-badge pass';
                        text.textContent = 'All assertions verified successfully';
                    } else {
                        badge.textContent = 'FAIL';
                        badge.className = 'verdict-badge fail';
                        text.textContent = 'One or more assertion rules failed';
                    }

                    const m = eventData.metrics || {};
                    document.getElementById('chip-latency').textContent = `Latency: ${(m.latency_sec || 0).toFixed(2)}s`;
                    document.getElementById('chip-speed').textContent = `Speed: ${(m.eval_tokens_per_sec || 0).toFixed(1)} tok/s`;
                    document.getElementById('chip-tokens').textContent = `Tokens: ${m.prompt_tokens || 0} + ${m.completion_tokens || 0}`;

                    assertContainer.innerHTML = '';
                    if (eventData.assertions && eventData.assertions.length) {
                        eventData.assertions.forEach(a => {
                            const item = document.createElement('div');
                            item.className = `eval-item ${a.passed ? 'pass' : 'fail'}`;
                            item.innerHTML = `
                                <span>${a.passed ? '✓' : '✗'}</span>
                                <span>${escapeHtml(a.message)}</span>
                            `;
                            assertContainer.appendChild(item);
                        });
                    } else {
                        assertContainer.innerHTML = '<span class="text-muted" style="font-size:0.8rem;">No assertions evaluated.</span>';
                    }
                } else if (eventData.type === 'error') {
                    streamFinished = true;
                    throw new Error(eventData.error || 'Server error during generation');
                }
            }
        }
        try { await reader.cancel(); } catch (_) {}
    } catch (e) {
        if (e.name === 'AbortError') {
            document.getElementById('sandbox-verdict').textContent = 'ABORTED';
            document.getElementById('sandbox-verdict').className = 'verdict-badge fail';
            document.getElementById('sandbox-verdict-text').textContent = 'Generation aborted by user';
        } else {
            document.getElementById('sandbox-verdict').textContent = 'ERR';
            document.getElementById('sandbox-verdict').className = 'verdict-badge fail';
            document.getElementById('sandbox-verdict-text').textContent = e.message;
            if (!rawOutput.textContent) {
                rawOutput.textContent = `Execution error: ${e.message}`;
            }
        }
    } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        sandboxAbortController = null;
    }
}

// ==============================================================================
// Utility Functions
// ==============================================================================

function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = 'toast';
    if (type === 'error') {
        toast.style.borderColor = 'var(--rose-500)';
    }
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 3200);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
