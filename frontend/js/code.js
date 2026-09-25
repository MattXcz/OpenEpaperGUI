// Code panel: shows the generated Jinja template, YAML and JSON payload.

import { state, setState } from './state.js';
import { api } from './api.js';
import { openPixelPreview } from './modals.js';
import { copyText } from './clipboard.js';

let output;
let warningsEl;
let statusEl;
let validateBtn;
let debounceTimer = null;

export function initCode() {
  output = document.getElementById('code-output');
  warningsEl = document.getElementById('code-warnings');
  statusEl = document.getElementById('code-status');
  validateBtn = document.getElementById('btn-validate');
  const renderBtn = document.getElementById('btn-render');
  if (renderBtn) renderBtn.addEventListener('click', () => openPixelPreview());

  document.querySelectorAll('[data-code]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-code]').forEach((b) => b.classList.remove('is-active'));
      button.classList.add('is-active');
      setState({ codeMode: button.dataset.code });
      paint();
    });
  });

  document.querySelectorAll('[data-copy]').forEach((button) => {
    button.addEventListener('click', async () => {
      const mode = button.dataset.copy;
      const text = mode === 'payload'
        ? JSON.stringify(state.generated.payload, null, 2)
        : state.generated[mode] || '';
      const label = button.dataset.label || (button.dataset.label = button.textContent);
      try {
        await copyText(text);
        button.textContent = 'Copied!';
      } catch {
        button.textContent = 'Copy failed';
      }
      setTimeout(() => { button.textContent = label; }, 1200);
    });
  });

  if (validateBtn) validateBtn.addEventListener('click', runValidation);

  paint();
}

export function scheduleGenerate() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(generate, 220);
}

async function generate() {
  if (!state.project) return;
  try {
    const result = await api.generate(state.project);
    state.generated = result;
    paint();
  } catch (error) {
    if (output) output.textContent = `// generation failed: ${error.message}`;
  }
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function renderStatus(node) {
  if (!statusEl) return;
  if (!node) {
    statusEl.hidden = true;
    statusEl.replaceChildren();
    return;
  }
  statusEl.hidden = false;
  statusEl.replaceChildren(...(Array.isArray(node) ? node : [node]));
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function showPending() {
  renderStatus(el('span', 'status-head', '⏳ Rendering the template…'));
  if (statusEl) statusEl.className = 'code-status is-pending';
}

function showResult(result) {
  const source = result.source === 'ha'
    ? 'rendered by Home Assistant'
    : 'rendered locally (Home Assistant not reachable)';

  if (result.ok) {
    if (statusEl) statusEl.className = 'code-status is-ok';
    renderStatus([
      el('div', 'status-head', `✓ Valid — ${result.count} element(s), ${source}`),
      result.haError ? el('div', 'status-detail', `Home Assistant fallback: ${result.haError}`) : null,
    ].filter(Boolean));
    return;
  }

  const stageLabel = {
    render: 'the template failed to render',
    parse: 'the rendered output is not valid JSON',
    elements: 'the payload contains invalid elements',
  }[result.stage] || 'validation failed';

  if (statusEl) statusEl.className = 'code-status is-error';
  const nodes = [el('div', 'status-head', `✕ Invalid — ${stageLabel}`)];

  // For element problems `error` is just a copy of the first issue, so only
  // show it when it carries something extra (the render/parse stages).
  const hasIssues = result.issues && result.issues.length;
  if (result.error && !hasIssues) nodes.push(el('div', 'status-detail', result.error));

  if (hasIssues) {
    const list = el('ul');
    for (const issue of result.issues) list.appendChild(el('li', null, issue));
    nodes.push(list);
  }

  if (result.excerpt) nodes.push(el('pre', null, result.excerpt));

  renderStatus(nodes);
}

async function runValidation() {
  if (!state.project || !validateBtn) return;
  validateBtn.disabled = true;
  const label = validateBtn.textContent;
  validateBtn.textContent = 'Checking…';
  showPending();
  try {
    const result = await api.validate(state.project);
    showResult(result);
  } catch (error) {
    if (statusEl) statusEl.className = 'code-status is-error';
    renderStatus(el('div', 'status-head', `✕ ${error.message}`));
  } finally {
    validateBtn.disabled = false;
    validateBtn.textContent = label;
  }
}

function paint() {
  if (!output) return;
  if (warningsEl) {
    const warnings = state.generated.warnings || [];
    warningsEl.hidden = !warnings.length;
    warningsEl.replaceChildren(...warnings.map((text) => {
      const line = document.createElement('div');
      line.textContent = `⚠ ${text}`;
      return line;
    }));
  }
  const mode = state.codeMode;
  if (mode === 'payload') {
    output.textContent = JSON.stringify(state.generated.payload || [], null, 2);
  } else {
    output.textContent = state.generated[mode] || '';
  }
}
