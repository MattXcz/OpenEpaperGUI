// Layers panel: tree view with reordering, grouping and visibility toggles.

import { state, setState, findNode, findParent, removeNode, typeSpec } from './state.js';
import { render } from './canvas.js';
import { elementLabel } from './renderer.js';
import { glyphFor } from './theme.js';

let container;

export function initLayers() {
  container = document.getElementById('layers');
  container.addEventListener('dragover', (event) => {
    if (!event.dataTransfer.types.includes('application/x-epaper-node')) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  });
  container.addEventListener('drop', (event) => {
    // Only handle drops that reached the container itself (not a group row).
    if (event.target !== container) return;
    const nodeId = event.dataTransfer.getData('application/x-epaper-node');
    if (nodeId) reparent(nodeId, null);
  });
  renderLayers();
}

export function renderLayers() {
  if (!container) return;
  container.innerHTML = '';
  const nodes = state.project?.nodes || [];

  if (!nodes.length) {
    container.innerHTML = '<p class="muted small">No elements yet. Drag one from the palette.</p>';
    return;
  }

  // Render top-most first (last drawn = on top).
  [...nodes].reverse().forEach((node) => {
    container.appendChild(buildLayer(node, nodes));
  });
}

function buildLayer(node, siblings) {
  const wrap = document.createElement('div');

  const row = document.createElement('div');
  row.className = 'layer';
  if (state.selection === node.id) row.classList.add('is-selected');
  if (node.kind === 'group') row.classList.add('is-group');

  const icon = document.createElement('span');
  icon.className = 'layer-icon';
  icon.textContent = node.kind === 'group' ? '⟳' : iconFor(node.type);

  const name = document.createElement('span');
  name.className = 'layer-name';
  name.textContent = elementLabel(node);

  const actions = document.createElement('span');
  actions.className = 'layer-actions';

  if (node.kind !== 'group') {
    const vis = document.createElement('button');
    vis.className = 'btn-icon';
    vis.title = 'Toggle visibility';
    vis.setAttribute('aria-label', vis.title);
    vis.textContent = node.props?.visible === false ? '🚫' : '👁';
    vis.addEventListener('click', (event) => {
      event.stopPropagation();
      node.props.visible = node.props?.visible === false;
      setState({ dirty: true }, 'structure');
      render();
      renderLayers();
    });
    actions.appendChild(vis);
  }

  const up = document.createElement('button');
  up.className = 'btn-icon';
  up.title = 'Bring forward';
  up.setAttribute('aria-label', up.title);
  up.textContent = '▲';
  up.addEventListener('click', (event) => {
    event.stopPropagation();
    move(node, siblings, 1);
  });

  const down = document.createElement('button');
  down.className = 'btn-icon';
  down.title = 'Send backward';
  down.setAttribute('aria-label', down.title);
  down.textContent = '▼';
  down.addEventListener('click', (event) => {
    event.stopPropagation();
    move(node, siblings, -1);
  });

  const del = document.createElement('button');
  del.className = 'btn-icon';
  del.title = 'Delete';
  del.setAttribute('aria-label', del.title);
  del.textContent = '✕';
  del.addEventListener('click', (event) => {
    event.stopPropagation();
    removeNode(node.id);
    if (state.selection === node.id) state.selection = null;
    setState({ dirty: true }, 'structure');
    render();
    renderLayers();
  });

  actions.append(up, down, del);
  row.append(icon, name, actions);

  // Drag & drop to re-parent: drop onto a group to move inside it,
  // drop onto the top-level list to pull out of a group.
  row.draggable = true;
  row.addEventListener('dragstart', (event) => {
    event.stopPropagation();
    event.dataTransfer.setData('application/x-epaper-node', node.id);
    event.dataTransfer.effectAllowed = 'move';
  });
  if (node.kind === 'group') {
    row.addEventListener('dragover', (event) => {
      if (!event.dataTransfer.types.includes('application/x-epaper-node')) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      row.style.borderColor = 'var(--accent)';
    });
    row.addEventListener('dragleave', () => {
      row.style.borderColor = '';
    });
    row.addEventListener('drop', (event) => {
      event.preventDefault();
      event.stopPropagation();
      row.style.borderColor = '';
      const draggedId = event.dataTransfer.getData('application/x-epaper-node');
      reparent(draggedId, node.id);
    });
  }

  row.addEventListener('click', () => {
    // 'structure' so the Inspector picks up the new selection too.
    setState({ selection: node.id }, 'structure');
  });
  wrap.appendChild(row);

  if (node.kind === 'group' && node.children?.length) {
    const children = document.createElement('div');
    children.className = 'layer-children';
    [...node.children].reverse().forEach((child) => {
      children.appendChild(buildLayer(child, node.children));
    });
    wrap.appendChild(children);
  }

  return wrap;
}

function move(node, siblings, direction) {
  const index = siblings.indexOf(node);
  const target = index + direction;
  if (target < 0 || target >= siblings.length) return;
  siblings.splice(index, 1);
  siblings.splice(target, 0, node);
  setState({ dirty: true }, 'structure');
  render();
  renderLayers();
}

/**
 * Moves a node into another group (or to the top level when targetId is null).
 * Guards against dropping a group into itself or its own descendants.
 */
function reparent(nodeId, targetId) {
  if (!nodeId || nodeId === targetId) return;
  const node = findNode(nodeId);
  if (!node) return;

  const target = targetId ? findNode(targetId) : null;
  if (target) {
    if (target.kind !== 'group') return;
    // Reject cycles (a group dropped into itself or its descendants).
    let cursor = target;
    while (cursor) {
      if (cursor.id === nodeId) return;
      cursor = findParent(cursor.id)?.parent || null;
    }
  }

  removeNode(nodeId);
  if (target) {
    target.children = target.children || [];
    target.children.push(node);
  } else {
    state.project.nodes.push(node);
  }

  setState({ selection: nodeId, dirty: true }, 'structure');
  render();
  renderLayers();
}

function iconFor(type) {
  return glyphFor(type, typeSpec(type));
}
