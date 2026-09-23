// Derives a bounding box (in display pixels) for every element type.
// The box is what the canvas uses for hit-testing, dragging and resizing.

import { state, typeSpec } from './state.js';

const CHAR_WIDTH = 0.58;   // monospace-ish advance per font-size unit
const LINE_HEIGHT = 1.25;

/**
 * Builds the variable context used to preview Jinja expressions.
 * Only literals declared in the project's Variables tab are known; entity
 * states obviously are not, so those stay unresolved.
 */
export function buildPreviewContext(project, extra = {}) {
  const ctx = { ...extra };
  for (const variable of project?.variables || []) {
    const name = String(variable.name || '').trim();
    if (!name || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) continue;
    const raw = String(variable.value ?? '').trim();
    if (raw === '') continue;
    if (/^-?\d+(\.\d+)?$/.test(raw)) {
      ctx[name] = Number(raw);
    } else if (/^\[.*\]$/.test(raw)) {
      // A list of plain numbers, e.g. [offset_0, offset_1, ...] is not usable,
      // but [110, 130, 150] is.
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) ctx[name] = parsed;
      } catch { /* leave unresolved */ }
    }
  }
  return ctx;
}

/**
 * Evaluates a restricted arithmetic expression. Returns null when the
 * expression references anything we cannot resolve (entity states, filters…).
 */
export function evalExpression(expr, ctx) {
  const source = String(expr).trim();

  // Number / simple literal.
  if (/^-?\d+(\.\d+)?$/.test(source)) return Number(source);

  // `offsets[i]` style lookups into a known list.
  const lookup = source.match(/^([A-Za-z_][A-Za-z0-9_]*)\[([A-Za-z0-9_]+)\]$/);
  if (lookup) {
    const list = ctx[lookup[1]];
    const index = ctx[lookup[2]];
    if (Array.isArray(list) && Number.isInteger(index) && index >= 0 && index < list.length) {
      const value = list[index];
      return typeof value === 'number' ? value : null;
    }
    return null;
  }

  // Only arithmetic over known numeric-ish identifiers is supported. Anything
  // containing a function call, filter, string literal or unknown name bails out.
  if (/['"()[\]{}|]/.test(source)) return null;

  const identifiers = source.match(/[A-Za-z_][A-Za-z0-9_]*/g) || [];
  for (const name of identifiers) {
    if (!(name in ctx)) return null;
    if (typeof ctx[name] !== 'number') return null;
  }
  if (!/^[\d\s+\-*/%().A-Za-z_]+$/.test(source)) return null;

  try {
    // Safe here: identifiers are all validated numbers and punctuation is arithmetic.
    // eslint-disable-next-line no-new-func
    const value = Function(...identifiers, `"use strict"; return (${source});`)(...identifiers.map((n) => ctx[n]));
    return typeof value === 'number' && Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

/**
 * Resolves every string property that is a `{{ … }}` expression into a plain
 * value when possible. Unresolvable properties are kept as-is.
 */
export function resolveProps(props, ctx) {
  const out = {};
  for (const [key, value] of Object.entries(props || {})) {
    if (typeof value !== 'string' || !value.includes('{{')) {
      out[key] = value;
      continue;
    }
    const whole = value.match(/^\s*\{\{\s*(.+?)\s*\}\}\s*$/s);
    if (whole) {
      const resolved = evalExpression(whole[1], ctx);
      out[key] = resolved === null ? value : resolved;
      continue;
    }
    // Mixed text with embedded expressions: substitute the ones we can.
    out[key] = value.replace(/\{\{\s*(.+?)\s*\}\}/g, (match, expr) => {
      const resolved = evalExpression(expr, ctx);
      return resolved === null ? match : String(resolved);
    });
  }
  return out;
}

function num(value, fallback = 0) {
  const parsed = typeof value === 'number' ? value : parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

// drawcustom accepts positions as a percentage of the canvas, e.g. "50%".
function coord(value, extent) {
  if (typeof value === 'string' && /^\s*-?\d+(\.\d+)?%\s*$/.test(value)) {
    return (parseFloat(value) / 100) * extent;
  }
  return num(value);
}
const cx = (value) => coord(value, state.project?.width || 0);
const cy = (value) => coord(value, state.project?.height || 0);

// Pillow text anchors: horizontal l/m/r, vertical a/t (top), m, s/b/d (bottom).
// Returns the fraction of the box that lies left of / above the anchor point.
function anchorFactors(anchor) {
  const a = String(anchor || '').toLowerCase();
  const fx = { l: 0, m: 0.5, r: 1 }[a[0]] ?? 0;
  const fy = { a: 0, t: 0, m: 0.5, s: 1, b: 1, d: 1 }[a[1]] ?? 0;
  return [fx, fy];
}

// Top-left corner of a box of size w×h whose anchor sits at (x, y).
// `anchorH` is the height the vertical anchor refers to: the whole box, or a
// single line for `multiline`, where HA anchors every line on its own.
function anchored(p, x, y, w, h, anchorH = h) {
  const [fx, fy] = anchorFactors(p.anchor);
  return { x: x - w * fx, y: y - anchorH * fy, w, h };
}

// Inverse of `anchored`: where the anchor point of `box` lies.
function anchorPoint(p, box, anchorH = box.h) {
  const [fx, fy] = anchorFactors(p.anchor);
  return { x: Math.round(box.x + box.w * fx), y: Math.round(box.y + anchorH * fy) };
}

// Lines of a text element; `multiline` drops newlines and splits on the
// delimiter, exactly like the HA image generator.
function textLines(p, g) {
  const text = String(p[g.text] ?? '');
  if (g.split) {
    const delimiter = String(p[g.split] ?? '');
    const flat = text.replace(/\n/g, '');
    return delimiter ? flat.split(delimiter) : [flat];
  }
  return text.split('\n');
}

function propsOf(node) {
  return node.__resolvedProps || node.props || {};
}

function textSize(text, size) {
  const lines = String(text ?? '').split('\n');
  const longest = lines.reduce((max, line) => Math.max(max, line.length), 0);
  return {
    w: Math.max(4, longest * size * CHAR_WIDTH),
    h: Math.max(4, lines.length * size * LINE_HEIGHT),
  };
}

/**
 * Returns { x, y, w, h } in display coordinates.
 */
export function boundsOf(node) {
  if (!node || node.kind === 'group') return null;
  const spec = typeSpec(node.type);
  if (!spec) return { x: 0, y: 0, w: 20, h: 20 };
  const p = propsOf(node);
  const g = spec.geometry || {};

  switch (g.kind) {
    case 'point': {
      const x = cx(p[g.x]);
      const y = cy(p[g.y]);

      if (g.radius) {
        const r = num(p[g.radius], 10);
        return { x: x - r, y: y - r, w: r * 2, h: r * 2 };
      }
      if (g.qr) {
        const box = num(p.boxsize, 2);
        const border = num(p.border, 1);
        // QR modules depend on data length; approximate a version-3 code (29 modules).
        const modules = 29 + border * 2;
        const side = modules * box;
        return { x, y, w: side, h: side };
      }
      if (g.w && g.h) {
        return { x, y, w: num(p[g.w], 40), h: num(p[g.h], 40) };
      }
      if (g.sequence) {
        const icons = Array.isArray(p[g.sequence]) ? p[g.sequence] : [];
        const size = num(p.size, 24);
        const spacing = p.spacing != null && p.spacing !== '' ? num(p.spacing) : size / 4;
        const count = Math.max(1, icons.length);
        const total = count * size + (count - 1) * spacing;
        const horizontal = (p.direction || 'right') === 'right' || (p.direction || 'right') === 'left';
        return horizontal
          ? anchored(p, x, y, total, size)
          : anchored(p, x, y, size, total);
      }
      if (g.square) {
        const size = num(p.size, 24);
        return anchored(p, x, y, size, size);
      }
      // text / multiline
      const size = num(p.size, 20);
      const lines = textLines(p, g);
      const measured = textSize(lines.join('\n'), size);
      if (g.line_step) {
        const lineH = size * LINE_HEIGHT;
        measured.h = (lines.length - 1) * num(p[g.line_step], 20) + lineH;
        return anchored(p, x, y, measured.w, measured.h, lineH);
      }
      return anchored(p, x, y, measured.w, measured.h);
    }

    case 'box': {
      const x1 = cx(p[g.x_start]);
      const y1 = cy(p[g.y_start]);
      const x2 = cx(p[g.x_end]);
      const y2 = cy(p[g.y_end]);
      const left = Math.min(x1, x2);
      const top = Math.min(y1, y2);
      const w = Math.abs(x2 - x1);
      const h = Math.abs(y2 - y1);
      if (g.line) {
        return { x: left, y: top, w: Math.max(w, 1), h: Math.max(h, 1) };
      }
      return { x: left, y: top, w: Math.max(w, 1), h: Math.max(h, 1) };
    }

    case 'pattern': {
      const xStart = cx(p[g.x_start]);
      const yStart = cy(p[g.y_start]);
      const xSize = num(p[g.x_size], 10);
      const ySize = num(p[g.y_size], 10);
      const xOffset = num(p[g.x_offset]);
      const yOffset = num(p[g.y_offset]);
      const xRepeat = Math.max(1, num(p[g.x_repeat], 1));
      const yRepeat = Math.max(1, num(p[g.y_repeat], 1));
      return {
        x: xStart,
        y: yStart,
        w: xRepeat * xSize + (xRepeat - 1) * xOffset,
        h: yRepeat * ySize + (yRepeat - 1) * yOffset,
      };
    }

    case 'points': {
      const points = Array.isArray(p[g.points]) ? p[g.points] : [];
      if (!points.length) return { x: 0, y: 0, w: 10, h: 10 };
      const xs = points.map((pt) => num(pt[0]));
      const ys = points.map((pt) => num(pt[1]));
      const minX = Math.min(...xs);
      const minY = Math.min(...ys);
      return {
        x: minX,
        y: minY,
        w: Math.max(1, Math.max(...xs) - minX),
        h: Math.max(1, Math.max(...ys) - minY),
      };
    }

    case 'full':
      return { x: 0, y: 0, w: 0, h: 0 };

    default:
      return { x: 0, y: 0, w: 20, h: 20 };
  }
}

/**
 * Applies a new bounding box back onto the element's props.
 * `mode` is 'move' or 'resize'.
 */
export function applyBounds(node, box, mode = 'move') {
  const spec = typeSpec(node.type);
  if (!spec) return;
  const g = spec.geometry || {};
  const p = node.props;

  if (g.kind === 'point') {
    if (g.radius) {
      const r = Math.max(1, Math.round(Math.max(box.w, box.h) / 2));
      p[g.radius] = r;
      p[g.x] = Math.round(box.x + r);
      p[g.y] = Math.round(box.y + r);
      return;
    }
    if (g.qr) {
      const border = num(p.border, 1);
      const modules = 29 + border * 2;
      p[g.size] = Math.max(1, Math.round(box.w / modules));
      p[g.x] = Math.round(box.x);
      p[g.y] = Math.round(box.y);
      return;
    }
    if (g.w && g.h) {
      p[g.w] = Math.max(1, Math.round(box.w));
      p[g.h] = Math.max(1, Math.round(box.h));
      p[g.x] = Math.round(box.x);
      p[g.y] = Math.round(box.y);
      return;
    }
    if (g.sequence) {
      const icons = Array.isArray(p[g.sequence]) ? p[g.sequence] : [];
      const count = Math.max(1, icons.length);
      const horizontal = (p.direction || 'right') === 'right' || (p.direction || 'right') === 'left';
      const total = horizontal ? box.w : box.h;
      const size = Math.max(1, Math.round((total - (count - 1) * (num(p.spacing) || 0)) / count));
      p[g.size] = size;
      Object.assign(p, keyed(g, anchorPoint(p, box)));
      return;
    }
    if (g.square) {
      const size = Math.max(1, Math.round(Math.max(box.w, box.h)));
      p[g.size] = size;
      Object.assign(p, keyed(g, anchorPoint(p, { ...box, w: size, h: size })));
      return;
    }
    // text / multiline
    const lines = textLines(p, g).length;
    const step = g.line_step ? num(p[g.line_step], 20) : 0;
    if (mode === 'resize') {
      const textH = g.line_step ? box.h - (lines - 1) * step : box.h / lines;
      p[g.size] = Math.max(1, Math.round(textH / LINE_HEIGHT));
    }
    const lineH = g.line_step ? num(p.size, 20) * LINE_HEIGHT : box.h;
    Object.assign(p, keyed(g, anchorPoint(p, box, lineH)));
    return;
  }

  if (g.kind === 'box') {
    p[g.x_start] = Math.round(box.x);
    p[g.y_start] = Math.round(box.y);
    p[g.x_end] = Math.round(box.x + box.w);
    p[g.y_end] = Math.round(box.y + box.h);
    return;
  }

  if (g.kind === 'pattern') {
    const xRepeat = Math.max(1, num(p[g.x_repeat], 1));
    const yRepeat = Math.max(1, num(p[g.y_repeat], 1));
    const xOffset = num(p[g.x_offset]);
    const yOffset = num(p[g.y_offset]);
    p[g.x_start] = Math.round(box.x);
    p[g.y_start] = Math.round(box.y);
    if (mode === 'resize') {
      p[g.x_size] = Math.max(1, Math.round((box.w - (xRepeat - 1) * xOffset) / xRepeat));
      p[g.y_size] = Math.max(1, Math.round((box.h - (yRepeat - 1) * yOffset) / yRepeat));
    }
    return;
  }

  if (g.kind === 'points') {
    const points = Array.isArray(p[g.points]) ? p[g.points] : [];
    if (!points.length) return;
    const current = boundsOf(node);
    const dx = box.x - current.x;
    const dy = box.y - current.y;
    const sx = current.w ? box.w / current.w : 1;
    const sy = current.h ? box.h / current.h : 1;
    p[g.points] = points.map((pt) => [
      Math.round(box.x + (num(pt[0]) - current.x) * sx),
      Math.round(box.y + (num(pt[1]) - current.y) * sy),
    ]);
  }
}

function keyed(g, point) {
  return { [g.x]: point.x, [g.y]: point.y };
}

export function snapValue(value, enabled, step = 2) {
  if (!enabled) return Math.round(value);
  return Math.round(value / step) * step;
}
