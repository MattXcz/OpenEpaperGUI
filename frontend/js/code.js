// Code panel: shows the generated Jinja template, YAML and JSON payload.

import { state, setState } from './state.js';
import { api } from './api.js';

let output;
let debounceTimer = null;

export function initCode() {
  output = document.getElementById('code-output');

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
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = 'Copied!';
        setTimeout(() => { button.textContent = `Copy ${mode === 'template' ? 'template' : mode.toUpperCase()}`; }, 1200);
      } catch {
        button.textContent = 'Copy failed';
      }
    });
  });

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

function paint() {
  if (!output) return;
  const mode = state.codeMode;
  if (mode === 'payload') {
    output.textContent = JSON.stringify(state.generated.payload || [], null, 2);
  } else {
    output.textContent = state.generated[mode] || '';
  }
}
