const state = {
  config: null,
  summary: null,
  sources: [],
  selectedSourceId: null,
  runs: [],
  tasks: [],
  selectedRunId: null,
  pollTimer: null,
};

const els = {
  runtimeRootText: document.getElementById('runtimeRootText'),
  dataRootText: document.getElementById('dataRootText'),
  taskChip: document.getElementById('taskChip'),
  sourceSearch: document.getElementById('sourceSearch'),
  sourceList: document.getElementById('sourceList'),
  summaryStrip: document.getElementById('summaryStrip'),
  selectedSourceName: document.getElementById('selectedSourceName'),
  selectedSourceType: document.getElementById('selectedSourceType'),
  selectedSourceEligibility: document.getElementById('selectedSourceEligibility'),
  selectedSourceNotes: document.getElementById('selectedSourceNotes'),
  sourceMetrics: document.getElementById('sourceMetrics'),
  maxPagesInput: document.getElementById('maxPagesInput'),
  pdfMaxPagesInput: document.getElementById('pdfMaxPagesInput'),
  ocrDpiInput: document.getElementById('ocrDpiInput'),
  dryRunInput: document.getElementById('dryRunInput'),
  candidateDiscoveryInput: document.getElementById('candidateDiscoveryInput'),
  ocrInput: document.getElementById('ocrInput'),
  crawlButton: document.getElementById('crawlButton'),
  discoverButton: document.getElementById('discoverButton'),
  actionFeedback: document.getElementById('actionFeedback'),
  runList: document.getElementById('runList'),
  eventTitle: document.getElementById('eventTitle'),
  eventList: document.getElementById('eventList'),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function formatDate(value) {
  if (!value) return 'In progress';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function selectedSource() {
  return state.sources.find((source) => source.source_id === state.selectedSourceId) || null;
}

function selectedRun() {
  return state.runs.find((run) => run.run_id === state.selectedRunId) || null;
}

function setFeedback(message, isError = false) {
  els.actionFeedback.textContent = message;
  els.actionFeedback.style.color = isError ? 'var(--danger)' : 'var(--muted)';
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function runToneClass(run) {
  const tone = run.result_tone || 'info';
  return `tone-${tone}`;
}

function runCardClass(run) {
  const tone = run.result_tone || 'info';
  return tone === 'warning' || tone === 'error' || tone === 'success' ? tone : 'info';
}

function formatRunStatus(run) {
  if (run.status === 'completed' && run.result_tone === 'warning') return 'completed with warnings';
  return run.status;
}

function renderSummary() {
  if (!state.summary) return;
  els.summaryStrip.innerHTML = [
    ['Approved Sources', state.summary.source_count],
    ['Completed Runs', state.summary.completed_runs],
    ['Quarantines', state.summary.quarantine_count],
    ['Chunk Records', state.summary.chunk_records ?? state.summary.chunk_files],
  ].map(([label, value]) => `
    <div class="summary-card">
      <p class="eyebrow">${label}</p>
      <strong>${value}</strong>
    </div>
  `).join('');

  els.runtimeRootText.textContent = state.summary.runtime_root;
  els.dataRootText.textContent = state.summary.data_root;

  const activeTasks = state.tasks.filter((task) => task.status === 'queued' || task.status === 'running');
  els.taskChip.textContent = activeTasks.length ? `${activeTasks.length} active task${activeTasks.length === 1 ? '' : 's'}` : 'No active tasks';
}

function renderSources() {
  const query = els.sourceSearch.value.trim().toLowerCase();
  const filtered = state.sources.filter((source) => {
    const haystack = `${source.source_name} ${source.source_id} ${source.source_family} ${source.license}`.toLowerCase();
    return haystack.includes(query);
  });

  if (!filtered.length) {
    els.sourceList.innerHTML = '<div class="empty-state">No sources match the current filter.</div>';
    return;
  }

  els.sourceList.innerHTML = filtered.map((source) => {
    const active = source.source_id === state.selectedSourceId ? 'active' : '';
    return `
      <button class="source-item ${active}" data-source-id="${source.source_id}">
        <div class="source-title">
          <span>${source.source_name}</span>
          <span class="stat-note">${source.source_type}</span>
        </div>
        <div class="source-meta">${source.license} | ${source.eligibility_class} | ${source.collectable ? 'ready' : 'blocked'}</div>
      </button>
    `;
  }).join('');

  els.sourceList.querySelectorAll('[data-source-id]').forEach((button) => {
    button.addEventListener('click', () => {
      state.selectedSourceId = button.dataset.sourceId;
      renderSources();
      renderSourceDetail();
    });
  });
}

function renderSourceDetail() {
  const source = selectedSource();
  if (!source) {
    els.selectedSourceName.textContent = 'Choose a source';
    els.selectedSourceType.textContent = 'Type';
    els.selectedSourceEligibility.textContent = 'Eligibility';
    els.selectedSourceNotes.textContent = 'Select an approved source to inspect scope, rights, and available actions.';
    els.sourceMetrics.innerHTML = '';
    els.crawlButton.disabled = true;
    els.discoverButton.disabled = true;
    return;
  }

  els.selectedSourceName.textContent = source.source_name;
  els.selectedSourceType.textContent = source.source_type;
  els.selectedSourceEligibility.textContent = source.eligibility_class;
  els.selectedSourceNotes.textContent = source.scope_notes || source.notes || 'No additional notes recorded.';

  const metrics = [
    ['Source ID', source.source_id],
    ['Family', source.source_family],
    ['License', source.license],
    ['Owner', source.owner],
    ['Seed URLs', source.seed_count],
    ['Artifacts', source.artifact_count],
    ['Review', source.review_status],
    ['Collection', source.collectable ? 'Allowed' : (source.collection_errors[0] || 'Blocked')],
  ];
  els.sourceMetrics.innerHTML = metrics.map(([label, value]) => `
    <div>
      <dt>${label}</dt>
      <dd>${value}</dd>
    </div>
  `).join('');

  const isPdf = source.source_type === 'pdf';
  els.candidateDiscoveryInput.disabled = isPdf;
  if (isPdf) {
    els.candidateDiscoveryInput.checked = false;
  }
  els.discoverButton.disabled = isPdf || !source.collectable;
  els.crawlButton.disabled = !source.collectable;
  els.ocrInput.disabled = !isPdf;
  els.pdfMaxPagesInput.disabled = !isPdf;
}

function renderRuns() {
  if (!state.runs.length) {
    els.runList.innerHTML = '<div class="empty-state">No runtime runs recorded yet.</div>';
    return;
  }

  els.runList.innerHTML = state.runs.map((run) => {
    const active = run.run_id === state.selectedRunId ? 'active' : '';
    const toneClass = runToneClass(run);
    const runClass = runCardClass(run);
    const emitted = run.emitted_chunks ?? run.summary_json?.emitted_chunks ?? run.summary_json?.chunk_files ?? 0;
    return `
      <button class="run-item ${active} ${runClass}" data-run-id="${run.run_id}">
        <div class="run-top">
          <span class="run-name">${run.job_id}</span>
          <span class="inline-status ${toneClass}">${formatRunStatus(run)}</span>
        </div>
        <div class="run-meta">${run.source_id || 'no source'} | started ${formatDate(run.started_at)}</div>
        <div class="run-meta ${toneClass}">Chunks ${emitted} | ${escapeHtml(run.result_message || run.error_text || 'No chunks emitted.')}</div>
      </button>
    `;
  }).join('');

  els.runList.querySelectorAll('[data-run-id]').forEach((button) => {
    button.addEventListener('click', async () => {
      state.selectedRunId = button.dataset.runId;
      renderRuns();
      await loadEvents(state.selectedRunId);
    });
  });
}

function renderEvents(events) {
  const run = selectedRun();
  els.eventTitle.textContent = run ? `${run.job_id} | ${run.run_id}` : 'Select a run';
  if (!events.length) {
    els.eventList.innerHTML = '<div class="empty-state">No events recorded for this run.</div>';
    return;
  }

  els.eventList.innerHTML = events.map((event) => {
    const levelClass = event.level === 'ERROR' ? 'error' : event.level === 'WARN' ? 'warning' : '';
    const payload = event.payload_json && Object.keys(event.payload_json).length
      ? `<div class="event-meta">${escapeHtml(JSON.stringify(event.payload_json))}</div>`
      : '';
    return `
      <div class="event-item ${levelClass}">
        <div class="event-top">
          <span class="event-type">${event.event_type}</span>
          <span class="stat-note ${levelClass ? `tone-${levelClass === 'error' ? 'error' : 'warning'}` : ''}">${event.level}</span>
        </div>
        <div class="event-meta">${formatDate(event.ts)}</div>
        <div class="event-meta">${escapeHtml(event.message)}</div>
        ${payload}
      </div>
    `;
  }).join('');
}

async function loadEvents(runId) {
  if (!runId) {
    renderEvents([]);
    return;
  }
  try {
    const events = await api(`/api/runs/${runId}/events`);
    renderEvents(events);
  } catch (error) {
    renderEvents([]);
    setFeedback(error.message, true);
  }
}

async function refreshAll() {
  const [config, summary, sources, runs, tasks] = await Promise.all([
    api('/api/config'),
    api('/api/summary'),
    api('/api/sources'),
    api('/api/runs?limit=20'),
    api('/api/tasks'),
  ]);

  state.config = config;
  state.summary = summary;
  state.sources = sources;
  state.runs = runs;
  state.tasks = tasks;

  if (!state.selectedSourceId && state.sources.length) {
    state.selectedSourceId = state.sources[0].source_id;
  }
  if (!state.selectedRunId && state.runs.length) {
    state.selectedRunId = state.runs[0].run_id;
  }

  renderSummary();
  renderSources();
  renderSourceDetail();
  renderRuns();
  await loadEvents(state.selectedRunId);
}

async function submitAction(action) {
  const source = selectedSource();
  if (!source) {
    setFeedback('Choose a source first.', true);
    return;
  }

  const payload = {
    source_id: source.source_id,
    dry_run: els.dryRunInput.checked,
    enable_candidate_discovery: els.candidateDiscoveryInput.checked,
    ocr: els.ocrInput.checked,
    ocr_dpi: els.ocrDpiInput.value,
    max_pages: els.maxPagesInput.value,
    pdf_max_pages: els.pdfMaxPagesInput.value,
  };

  try {
    setFeedback(`Submitting ${action} for ${source.source_id}...`);
    const task = await api(`/api/actions/${action}`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    state.selectedRunId = task.run_id;
    await refreshAll();
    setFeedback(`Queued ${action} for ${source.source_id}.`);
  } catch (error) {
    setFeedback(error.message, true);
  }
}

async function init() {
  els.sourceSearch.addEventListener('input', renderSources);
  els.crawlButton.addEventListener('click', () => submitAction('crawl'));
  els.discoverButton.addEventListener('click', () => submitAction('discover'));

  try {
    await refreshAll();
    setFeedback('Ready.');
  } catch (error) {
    setFeedback(error.message, true);
  }

  state.pollTimer = window.setInterval(async () => {
    try {
      await refreshAll();
    } catch {
      // Keep the UI stable if polling fails briefly.
    }
  }, 5000);
}

init();
