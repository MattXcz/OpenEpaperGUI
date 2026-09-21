// Application entry point: wires the palette, canvas, panels and toolbar.

import { api } from './api.js';
import {
  state, setState, subscribe, createProject, createElement, createGroup,
  findNode, removeNode, typeSpec,
} from './state.js';
import {
  initCanvas, render, addElement, addGroup, deleteSelected, duplicateSelected,
  nudgeSelected, centerSelected, scrollToFit,
} from './canvas.js';
import { initInspector, renderInspector } from './inspector.js';
import { initLayers, renderLayers } from './layers.js';
import { initVariables, renderVariables } from './variables.js';
import { initCode, scheduleGenerate } from './code.js';
import {
  openProjects, openSettings, openExport, openPush, toast, closeModal,
} from './modals.js';

let saveTimer = null;

async function boot() {
  try {
    state.schema = await api.schema();
  } catch (error) {
    document.body.innerHTML = `<div style="padding:40px;font-family:sans-serif;color:#eee;background:#0f1115;height:100vh;">
      <h2>Cannot reach the backend</h2><p>${error.message}</p></div>`;
    return;
  }

  try {
    state.settings = await api.getSettings();
  } catch { /* optional */ }

  state.project = createProject('Untitled');

  buildPalette();
  buildDisplayPresets();
  initCanvas();
  initInspector();
  initLayers();
  initVariables();
  initCode();
  wireToolbar();
  wireTabs();
  wireKeyboard();
  wireProjectName();

  subscribe(onStateChange);

  render();
  renderInspector();
  renderLayers();
  renderVariables();
  scheduleGenerate();
  scrollToFit();
  updateSaveState();
}

// ---------------------------------------------------------------------------
// Palette
// ---------------------------------------------------------------------------

function buildPalette() {
  const host = document.getElementById('palette');
  const search = document.getElementById('palette-search');

  const paint = (filter = '') => {
    host.innerHTML = '';
    const needle = filter.trim().toLowerCase();
    const groups = new Map();

    for (const spec of state.schema.types) {
      if (needle && !spec.label.toLowerCase().includes(needle) && !spec.type.includes(needle)) continue;
      if (!groups.has(spec.category)) groups.set(spec.category, []);
      groups.get(spec.category).push(spec);
    }

    for (const [category, specs] of groups) {
      const group = document.createElement('div');
      group.className = 'palette-group';
      group.innerHTML = `<div class="palette-group-title">${category}</div>`;
      const items = document.createElement('div');
      items.className = 'palette-items';

      for (const spec of specs) {
        const item = document.createElement('div');
        item.className = 'palette-item';
        item.draggable = true;
        item.title = `Drag onto the canvas — ${spec.type}`;
        item.innerHTML = `<span class="pi-icon">${iconFor(spec)}</span><span>${spec.label}</span>`;

        item.addEventListener('dragstart', (event) => {
          event.dataTransfer.setData('application/x-epaper-type', spec.type);
          event.dataTransfer.effectAllowed = 'copy';
        });
        item.addEventListener('dblclick', () => {
          addElement(spec.type);
          scheduleGenerate();
        });
        items.appendChild(item);
      }
      group.appendChild(items);
      host.appendChild(group);
    }

    // Repeat group is a structural node, not a draw type.
    const group = document.createElement('div');
    group.className = 'palette-group';
    group.innerHTML = '<div class="palette-group-title">Structure</div>';
    const items = document.createElement('div');
    items.className = 'palette-items';
    const item = document.createElement('div');
    item.className = 'palette-item';
    item.style.gridColumn = 'span 2';
    item.innerHTML = '<span class="pi-icon">⟳</span><span>Repeat group (Jinja loop)</span>';
    item.addEventListener('click', () => {
      addGroup();
      scheduleGenerate();
    });
    items.appendChild(item);
    group.appendChild(items);
    host.appendChild(group);
  };

  paint();
  search.addEventListener('input', () => paint(search.value));
}

function iconFor(spec) {
  const map = {
    text: 'T', multiline: '≡', icon: '★', icon_sequence: '⋯', qrcode: '▦',
    dlimg: '🖼', line: '─', rectangle: '▭', rectangle_pattern: '▦',
    polygon: '⬟', circle: '○', ellipse: '⬭', arc: '◔',
    progress_bar: '▰', plot: '📈', debug_grid: '▩',
  };
  return map[spec.type] || '◆';
}

// ---------------------------------------------------------------------------
// Display presets
// ---------------------------------------------------------------------------

function buildDisplayPresets() {
  const select = document.getElementById('display-preset');
  for (const preset of state.schema.displayPresets) {
    const option = document.createElement('option');
    option.value = `${preset.width}x${preset.height}`;
    option.textContent = preset.label;
    select.appendChild(option);
  }
  select.value = `${state.project.width}x${state.project.height}`;

  select.addEventListener('change', () => {
    const [w, h] = select.value.split('x').map(Number);
    if (!Number.isFinite(w) || !Number.isFinite(h)) return;
    state.project.width = w;
    state.project.height = h;
    document.getElementById('display-width').value = w;
    document.getElementById('display-height').value = h;
    setState({ dirty: true }, 'structure');
    render();
    scrollToFit();
    scheduleGenerate();
  });

  const width = document.getElementById('display-width');
  const height = document.getElementById('display-height');
  width.value = state.project.width;
  height.value = state.project.height;

  const applySize = () => {
    const w = Math.max(16, Number(width.value) || 296);
    const h = Math.max(16, Number(height.value) || 128);
    state.project.width = w;
    state.project.height = h;
    select.value = `${w}x${h}`;
    setState({ dirty: true }, 'structure');
    render();
    scheduleGenerate();
  };
  width.addEventListener('change', applySize);
  height.addEventListener('change', applySize);

  document.getElementById('display-background').addEventListener('change', (event) => {
    state.project.background = event.target.value;
    setState({ dirty: true }, 'structure');
    render();
    scheduleGenerate();
  });
}

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

function wireToolbar() {
  document.getElementById('btn-projects').addEventListener('click', () => {
    openProjects((project) => loadProject(project));
  });
  document.getElementById('btn-settings').addEventListener('click', () => openSettings());
  document.getElementById('btn-export').addEventListener('click', () => openExport());
  document.getElementById('btn-push').addEventListener('click', () => openPush());

  const zoom = document.getElementById('zoom');
  zoom.value = Math.round(state.zoom * 100);
  zoom.addEventListener('change', () => {
    const value = Math.min(400, Math.max(25, Number(zoom.value) || 100));
    setState({ zoom: value / 100 }, 'zoom');
    render();
  });

  const gridBtn = document.getElementById('btn-grid');
  gridBtn.classList.toggle('is-active', state.showGrid);
  gridBtn.addEventListener('click', () => {
    state.showGrid = !state.showGrid;
    gridBtn.classList.toggle('is-active', state.showGrid);
    render();
  });

  const snapBtn = document.getElementById('btn-snap');
  snapBtn.classList.toggle('is-active', state.snap);
  snapBtn.addEventListener('click', () => {
    state.snap = !state.snap;
    snapBtn.classList.toggle('is-active', state.snap);
  });

  const previewBtn = document.getElementById('btn-preview');
  previewBtn.addEventListener('click', () => {
    state.preview = !state.preview;
    previewBtn.classList.toggle('is-active', state.preview);
    render();
  });
}

function wireTabs() {
  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach((t) => t.classList.remove('is-active'));
      document.querySelectorAll('.tab-panel').forEach((p) => p.classList.remove('is-active'));
      tab.classList.add('is-active');
      document.querySelector(`[data-panel="${tab.dataset.tab}"]`).classList.add('is-active');
      if (tab.dataset.tab === 'layers') renderLayers();
      if (tab.dataset.tab === 'variables') renderVariables();
      if (tab.dataset.tab === 'code') scheduleGenerate();
    });
  });
}

function wireProjectName() {
  const input = document.getElementById('project-name');
  input.value = state.project.name;
  input.addEventListener('input', () => {
    state.project.name = input.value;
    setState({ dirty: true }, 'change');
  });
}

function wireKeyboard() {
  window.addEventListener('keydown', (event) => {
    const tag = document.activeElement?.tagName;
    const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';

    if (event.key === 'Escape') {
      closeModal();
      if (!typing) {
        setState({ selection: null });
        render();
      }
      return;
    }

    if (typing) return;

    if (event.key === 'Delete' || event.key === 'Backspace') {
      event.preventDefault();
      deleteSelected();
      scheduleGenerate();
      return;
    }

    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'd') {
      event.preventDefault();
      duplicateSelected();
      scheduleGenerate();
      return;
    }

    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveProject();
      return;
    }

    const step = event.shiftKey ? 10 : 1;
    if (event.key === 'ArrowLeft') { event.preventDefault(); nudgeSelected(-step, 0); scheduleGenerate(); }
    if (event.key === 'ArrowRight') { event.preventDefault(); nudgeSelected(step, 0); scheduleGenerate(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); nudgeSelected(0, -step); scheduleGenerate(); }
    if (event.key === 'ArrowDown') { event.preventDefault(); nudgeSelected(0, step); scheduleGenerate(); }
    if (event.key.toLowerCase() === 'c') { centerSelected(); scheduleGenerate(); }
  });
}

// ---------------------------------------------------------------------------
// State reactions
// ---------------------------------------------------------------------------

function onStateChange(event) {
  if (event === 'structure') {
    renderLayers();
    renderInspector();
  }
  if (event === 'change' || event === 'structure' || event === 'drag') {
    scheduleGenerate();
    scheduleSave();
  }
  if (event === 'zoom') {
    document.getElementById('zoom').value = Math.round(state.zoom * 100);
  }
  updateSaveState();
}

function updateSaveState() {
  const el = document.getElementById('save-state');
  if (!el) return;
  el.textContent = state.dirty ? 'unsaved' : 'saved';
  el.classList.toggle('is-dirty', state.dirty);
  el.classList.toggle('is-saved', !state.dirty);
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveProject, 1500);
}

async function saveProject() {
  if (!state.project) return;
  try {
    // Strip editor-only preview metadata (keys prefixed with "__").
    const payload = JSON.parse(JSON.stringify(state.project, (key, value) =>
      key.startsWith('__') ? undefined : value));
    const saved = state.project.id
      ? await api.updateProject(state.project.id, payload)
      : await api.createProject(payload);
    state.project.id = saved.id;
    state.dirty = false;
    updateSaveState();
  } catch {
    // Autosave failures are non-fatal; the user can still export.
  }
}

function loadProject(project) {
  state.project = {
    id: project.id || null,
    name: project.name || 'Untitled',
    width: project.width || 296,
    height: project.height || 128,
    background: project.background || 'white',
    nodes: project.nodes || [],
    variables: project.variables || [],
  };
  state.selection = null;
  state.dirty = false;

  document.getElementById('project-name').value = state.project.name;
  document.getElementById('display-width').value = state.project.width;
  document.getElementById('display-height').value = state.project.height;
  document.getElementById('display-background').value = state.project.background;
  document.getElementById('display-preset').value = `${state.project.width}x${state.project.height}`;

  render();
  renderInspector();
  renderLayers();
  renderVariables();
  scheduleGenerate();
  scrollToFit();
  updateSaveState();
}

boot();
