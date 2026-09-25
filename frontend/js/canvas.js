// Canvas: renders the display, handles drag & drop, selection, move and resize.

import {
  state, setState, createElement, createGroup, findNode, findParent, removeNode, emit, typeSpec,
  uid,
} from './state.js';
import { boundsOf, applyBounds, snapValue, buildPreviewContext, resolveProps } from './geometry.js';
import { renderElementContent, elementLabel } from './renderer.js';
import { FONT_FAMILY_NAMES } from './theme.js';

let canvasEl;
let elementsEl;
let overlayEl;
let gridEl;
let scrollEl;
let drag = null;

export function initCanvas() {
  canvasEl = document.getElementById('canvas');
  elementsEl = document.getElementById('canvas-elements');
  overlayEl = document.getElementById('canvas-overlay');
  gridEl = document.getElementById('canvas-grid');
  scrollEl = document.getElementById('canvas-scroll');

  // Text boxes are measured with the display fonts; redraw once they arrive.
  if (document.fonts) {
    Promise.all(FONT_FAMILY_NAMES.map((family) => document.fonts.load(`16px "${family}"`)))
      .then(() => render())
      .catch(() => { /* keep the estimated widths */ });
  }

  // Drop from the palette.
  canvasEl.addEventListener('dragover', (event) => {
    if (event.dataTransfer.types.includes('application/x-epaper-type')) {
      event.preventDefault();
      event.dataTransfer.dropEffect = 'copy';
    }
  });

  canvasEl.addEventListener('drop', (event) => {
    const type = event.dataTransfer.getData('application/x-epaper-type');
    if (!type) return;
    event.preventDefault();
    const point = toDisplayCoords(event);
    const element = createElement(type);
    placeElementAt(element, point);

    // Dropping while a repeat group is selected adds the element to that group.
    const selected = state.selection ? findNode(state.selection) : null;
    if (selected && selected.kind === 'group') {
      selected.children = selected.children || [];
      selected.children.push(element);
    } else {
      state.project.nodes.push(element);
    }

    setState({ selection: element.id, dirty: true }, 'structure');
    render();
  });

  // Click empty canvas clears selection.
  canvasEl.addEventListener('mousedown', (event) => {
    if (event.target === canvasEl || event.target === elementsEl || event.target === gridEl) {
      setState({ selection: null });
      render();
    }
  });

  // Track pointer for the coordinate readout.
  canvasEl.addEventListener('mousemove', (event) => {
    const point = toDisplayCoords(event);
    const readout = document.getElementById('status-coords');
    if (readout) readout.textContent = `x: ${Math.round(point.x)}  y: ${Math.round(point.y)}`;
  });

  window.addEventListener('mousemove', onDragMove);
  window.addEventListener('mouseup', onDragEnd);

  render();
}

function toDisplayCoords(event) {
  const rect = canvasEl.getBoundingClientRect();
  const zoom = state.zoom;
  return {
    x: (event.clientX - rect.left) / zoom,
    y: (event.clientY - rect.top) / zoom,
  };
}

function placeElementAt(element, point) {
  const spec = state.schema?.types.find((t) => t.type === element.type);
  const g = spec?.geometry || {};
  const p = element.props;
  const x = snapValue(point.x, state.snap);
  const y = snapValue(point.y, state.snap);

  if (g.kind === 'point') {
    if (g.radius) {
      const r = Number(p[g.radius]) || 20;
      p[g.x] = x + r;
      p[g.y] = y + r;
    } else {
      p[g.x] = x;
      p[g.y] = y;
    }
    return;
  }
  if (g.kind === 'box') {
    const w = Math.abs((Number(p[g.x_end]) || 0) - (Number(p[g.x_start]) || 0)) || 60;
    // A line's zero height is what makes it horizontal, not a missing size.
    const h = Math.abs((Number(p[g.y_end]) || 0) - (Number(p[g.y_start]) || 0)) || (g.line ? 0 : 30);
    p[g.x_start] = x;
    p[g.y_start] = y;
    p[g.x_end] = x + w;
    p[g.y_end] = y + h;
    return;
  }
  if (g.kind === 'pattern') {
    p[g.x_start] = x;
    p[g.y_start] = y;
    return;
  }
  if (g.kind === 'points') {
    const points = Array.isArray(p[g.points]) ? p[g.points] : [];
    if (!points.length) return;
    const minX = Math.min(...points.map((pt) => Number(pt[0])));
    const minY = Math.min(...points.map((pt) => Number(pt[1])));
    p[g.points] = points.map((pt) => [Number(pt[0]) - minX + x, Number(pt[1]) - minY + y]);
  }
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

export function render() {
  if (!canvasEl) return;
  const project = state.project;
  if (!project) return;

  canvasEl.style.width = `${project.width}px`;
  canvasEl.style.height = `${project.height}px`;
  canvasEl.style.background = project.background === 'black' ? '#000' : '#fff';
  canvasEl.style.transform = `scale(${state.zoom})`;
  canvasEl.classList.toggle('is-preview', state.preview);
  gridEl.classList.toggle('is-hidden', !state.showGrid);

  elementsEl.innerHTML = '';
  overlayEl.innerHTML = '';

  // Drop stale preview values so edits to props are always reflected.
  for (const node of flatten(project.nodes)) {
    delete node.__display;
    delete node.__approximate;
    if (node.kind !== 'group') delete node.__resolvedProps;
  }

  computePreviewLayout(project);

  const flat = flatten(project.nodes);
  flat.forEach((node, index) => {
    elementsEl.appendChild(buildElementNode(node, index));
  });

  // Draw the selection overlay on top.
  const selected = state.selection ? findNode(state.selection) : null;
  if (selected && selected.kind !== 'group') {
    const box = boundsOf(selected);
    if (box) {
      const outline = document.createElement('div');
      outline.className = 'selection-outline';
      outline.style.cssText = `position:absolute;left:${box.x}px;top:${box.y}px;width:${box.w}px;height:${box.h}px;border:1.5px solid var(--accent);pointer-events:none;`;
      overlayEl.appendChild(outline);
    }
  }
}

function flatten(nodes, depth = 0, out = []) {
  for (const node of nodes) {
    out.push(node);
    if (node.children) flatten(node.children, depth + 1, out);
  }
  return out;
}

function isDynamic(value) {
  return typeof value === 'string' && /\{\{|\{%/.test(value);
}

/**
 * Preview of loop contents. Home Assistant renders the real thing; here we
 * evaluate every `{{ … }}` coordinate we can with the loop variable pinned to
 * its first iteration, so a repeat group looks like its first column instead of
 * collapsing onto the origin.
 *
 * Anything that still cannot be resolved (entity states, filters) is marked
 * approximate: it stays selectable and editable, but is not draggable because
 * Home Assistant owns its final position.
 */
function computePreviewLayout(project) {
  layoutGroups(project.nodes, buildPreviewContext(project));
}

// Groups can be nested; every loop level pins its own variable to 0 and sees
// the variables of the loops around it.
function layoutGroups(nodes, parentCtx) {
  for (const node of nodes) {
    if (node.kind !== 'group') continue;

    const ctx = { ...parentCtx };
    if (node.repeat?.enabled !== false) {
      const repeatVar = String(node.repeat?.var || 'i').trim() || 'i';
      ctx[repeatVar] = 0;

      // `{% set %}` statements run before the loop body.
      for (const statement of node.repeat?.pre || []) {
        const match = String(statement).match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$/);
        if (!match) continue;
        const [, name, expr] = match;
        try {
          const parsed = JSON.parse(expr);
          if (Array.isArray(parsed)) ctx[name] = parsed;
        } catch { /* not a literal list */ }
      }
    }

    for (const child of node.children || []) {
      if (child.kind === 'group') continue;
      child.__resolvedProps = resolveProps(child.props, ctx);
      child.__display = null;
      child.__approximate = childHasUnresolvedGeometry(child);
    }
    layoutGroups(node.children || [], ctx);
  }
}

function childHasUnresolvedGeometry(node) {
  const spec = typeSpec(node.type);
  if (!spec) return false;
  const g = spec.geometry || {};
  const p = node.__resolvedProps || node.props || {};
  const keys = [g.x, g.y, g.radius, g.x_start, g.y_start, g.x_end, g.y_end].filter(Boolean);
  return keys.some((key) => isDynamic(p[key]));
}

function buildElementNode(node, index) {
  const wrapper = document.createElement('div');
  wrapper.className = 'el';
  wrapper.dataset.id = node.id;
  wrapper.style.zIndex = String(index + 1);

  if (node.kind === 'group') {
    const box = groupBounds(node);
    wrapper.style.cssText += `left:${box.x}px;top:${box.y}px;width:${box.w}px;height:${box.h}px;`;
    wrapper.classList.add('is-group');
    wrapper.innerHTML = `
      <div class="el-box" style="border-color:var(--warning);border-style:solid;"></div>
      <div class="el-label" style="color:var(--warning);">⟳ ${escapeHtml(node.name || 'group')} × ${escapeHtml(String(node.repeat?.count ?? 1))}</div>
    `;
  } else {
    const box = node.__display || boundsOf(node);
    if (!box) return wrapper;
    wrapper.style.cssText += `left:${box.x}px;top:${box.y}px;width:${box.w}px;height:${box.h}px;`;
    const hidden = node.props?.visible === false;
    if (hidden) wrapper.classList.add('is-hidden-el');
    const approximate = node.__approximate;
    if (approximate) wrapper.classList.add('is-approximate');
    wrapper.innerHTML = `
      <div class="el-content">${renderElementContent(node)}</div>
      <div class="el-box"></div>
      <div class="el-label">${escapeHtml(elementLabel(node))}${approximate ? ' · dynamic' : ''}</div>
      ${approximate ? '' : '<div class="el-handle" data-handle="se"></div><div class="el-handle" data-handle="e"></div><div class="el-handle" data-handle="s"></div>'}
    `;
  }

  if (state.selection === node.id) wrapper.classList.add('is-selected');

  wrapper.addEventListener('mousedown', (event) => {
    event.stopPropagation();
    // Elements positioned by Jinja that we could not evaluate cannot be dragged.
    if (node.__approximate) {
      setState({ selection: node.id });
      render();
      return;
    }
    if (event.target.dataset.handle) {
      startDrag(event, node, event.target.dataset.handle);
    } else {
      startDrag(event, node, 'move');
    }
  });

  return wrapper;
}

function groupBounds(group) {
  const boxes = (group.children || [])
    .map((child) => (child.kind === 'group' ? groupBounds(child) : child.__display || boundsOf(child)))
    .filter(Boolean);
  if (!boxes.length) return { x: 0, y: 0, w: 40, h: 40 };
  const minX = Math.min(...boxes.map((b) => b.x));
  const minY = Math.min(...boxes.map((b) => b.y));
  const maxX = Math.max(...boxes.map((b) => b.x + b.w));
  const maxY = Math.max(...boxes.map((b) => b.y + b.h));
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ---------------------------------------------------------------------------
// Dragging
// ---------------------------------------------------------------------------

function startDrag(event, node, mode) {
  event.preventDefault();
  setState({ selection: node.id });

  const start = toDisplayCoords(event);
  const targets = collectTargets(node);
  drag = {
    mode,
    start,
    targets: targets.map((target) => ({
      node: target,
      origin: { ...boundsOf(target) },
    })),
  };
  render();
}

function collectTargets(node) {
  if (node.kind === 'group') {
    return (node.children || []).flatMap((child) => collectTargets(child));
  }
  return node.__approximate ? [] : [node];
}

function onDragMove(event) {
  if (!drag) return;
  const point = toDisplayCoords(event);
  const dx = point.x - drag.start.x;
  const dy = point.y - drag.start.y;

  for (const target of drag.targets) {
    const origin = target.origin;
    let box;
    if (drag.mode === 'move') {
      box = {
        x: snapValue(origin.x + dx, state.snap),
        y: snapValue(origin.y + dy, state.snap),
        w: origin.w,
        h: origin.h,
      };
    } else {
      let w = origin.w;
      let h = origin.h;
      if (drag.mode === 'se' || drag.mode === 'e') w = Math.max(4, snapValue(origin.w + dx, state.snap));
      if (drag.mode === 'se' || drag.mode === 's') h = Math.max(4, snapValue(origin.h + dy, state.snap));
      box = { x: origin.x, y: origin.y, w, h };
    }
    applyBounds(target.node, box, drag.mode === 'move' ? 'move' : 'resize');
  }

  render();
  emit('drag');
}

function onDragEnd() {
  if (!drag) return;
  drag = null;
  setState({ dirty: true }, 'change');
  render();
}

// ---------------------------------------------------------------------------
// Public helpers
// ---------------------------------------------------------------------------

export function addElement(type, at = null) {
  const element = createElement(type);
  const point = at || {
    x: Math.round(state.project.width / 2 - 40),
    y: Math.round(state.project.height / 2 - 15),
  };
  placeElementAt(element, point);
  state.project.nodes.push(element);
  setState({ selection: element.id, dirty: true }, 'structure');
  render();
  return element;
}

export function addGroup() {
  const group = createGroup([]);
  state.project.nodes.push(group);
  setState({ selection: group.id, dirty: true }, 'structure');
  render();
  return group;
}

export function deleteSelected() {
  if (!state.selection) return;
  removeNode(state.selection);
  setState({ selection: null, dirty: true }, 'structure');
  render();
}

export function duplicateSelected() {
  const node = state.selection ? findNode(state.selection) : null;
  if (!node) return;
  const clone = JSON.parse(JSON.stringify(node, (key, value) =>
    (key.startsWith('__') ? undefined : value)));
  // Every node in the copy needs a fresh id, children included: duplicate ids
  // make selection and the layer tree act on the wrong node.
  const reId = (item) => {
    item.id = uid(item.kind === 'group' ? 'grp' : 'el');
    (item.children || []).forEach(reId);
  };
  reId(clone);
  if (clone.kind !== 'group') {
    const box = boundsOf(node);
    applyBounds(clone, { x: box.x + 10, y: box.y + 10, w: box.w, h: box.h });
  }
  // The copy goes right above the original, in the same parent.
  const location = findParent(node.id);
  const siblings = location ? location.list : state.project.nodes;
  siblings.splice(location ? location.index + 1 : siblings.length, 0, clone);
  setState({ selection: clone.id, dirty: true }, 'structure');
  render();
}

export function nudgeSelected(dx, dy) {
  const node = state.selection ? findNode(state.selection) : null;
  if (!node) return;
  const targets = collectTargets(node);
  for (const target of targets) {
    const box = boundsOf(target);
    applyBounds(target, { x: box.x + dx, y: box.y + dy, w: box.w, h: box.h });
  }
  setState({ dirty: true }, 'change');
  render();
}

export function centerSelected() {
  const node = state.selection ? findNode(state.selection) : null;
  if (!node) return;
  const targets = collectTargets(node);
  for (const target of targets) {
    const box = boundsOf(target);
    applyBounds(target, {
      x: Math.round((state.project.width - box.w) / 2),
      y: box.y,
      w: box.w,
      h: box.h,
    });
  }
  setState({ dirty: true }, 'change');
  render();
}

export function scrollToFit() {
  if (!scrollEl) return;
  const project = state.project;
  const available = scrollEl.clientWidth - 56;
  const availableH = scrollEl.clientHeight - 56;
  const zoom = Math.min(available / project.width, availableH / project.height, 2);
  setState({ zoom: Math.max(0.25, Math.round(zoom * 20) / 20) }, 'zoom');
  render();
}
