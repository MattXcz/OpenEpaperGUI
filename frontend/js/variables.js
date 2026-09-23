// Variables panel: project-level `{% set %}` definitions.

import { state, setState } from './state.js';

let container;

export function initVariables() {
  container = document.getElementById('variables');
  document.getElementById('btn-add-variable').addEventListener('click', () => {
    state.project.variables.push({ name: `var_${state.project.variables.length + 1}`, value: '' });
    setState({ dirty: true }, 'structure');
    renderVariables();
  });
  renderVariables();
}

export function renderVariables() {
  if (!container) return;
  container.innerHTML = '';
  const variables = state.project?.variables || [];

  if (!variables.length) {
    container.innerHTML = '<p class="muted small">No variables defined.</p>';
    return;
  }

  variables.forEach((variable, index) => {
    const row = document.createElement('div');
    row.className = 'variable-row';

    const fields = document.createElement('div');
    fields.className = 'var-fields';

    const name = document.createElement('input');
    name.className = 'input';
    name.placeholder = 'name';
    name.value = variable.name || '';
    name.addEventListener('input', () => {
      variable.name = name.value;
      setState({ dirty: true }, 'change');
    });

    const value = document.createElement('input');
    value.className = 'input';
    value.placeholder = 'value or expression, e.g. 49';
    value.value = variable.value ?? '';
    value.addEventListener('input', () => {
      variable.value = value.value;
      setState({ dirty: true }, 'change');
    });

    fields.append(name, value);

    const del = document.createElement('button');
    del.className = 'btn-icon';
    del.textContent = '✕';
    del.title = 'Remove';
    del.addEventListener('click', () => {
      variables.splice(index, 1);
      setState({ dirty: true }, 'structure');
      renderVariables();
    });

    row.append(fields, del);
    container.appendChild(row);
  });
}
