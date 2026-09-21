// Derives a bounding box (in display pixels) for every element type.
// The box is what the canvas uses for hit-testing, dragging and resizing.

import { typeSpec } from './state.js';

const CHAR_WIDTH = 0.58;   // monospace-ish advance per font-size unit
const LINE_HEIGHT = 1.25;

function num(value, fallback = 0) {
  const parsed = typeof value === 'number' ? value : parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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
  const p = node.props || {};
  const g = spec.geometry || {};

  switch (g.kind) {
    case 'point': {
      const x = num(p[g.x]);
      const y = num(p[g.y]);

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
          ? { x, y, w: total, h: size }
          : { x, y, w: size, h: total };
      }
      if (g.square) {
        const size = num(p.size, 24);
        return { x, y, w: size, h: size };
      }
      // text / multiline
      const size = num(p.size, 20);
      let text = String(p[g.text] ?? '');
      if (g.split && p[g.split]) {
        text = text.split(String(p[g.split])).join('\n');
      }
      const measured = textSize(text, size);
      if (g.line_step && text.includes('\n')) {
        const lines = text.split('\n').length;
        measured.h = (lines - 1) * num(p[g.line_step], 20) + size * LINE_HEIGHT;
      }
      return { x, y, w: measured.w, h: measured.h };
    }

    case 'box': {
      const x1 = num(p[g.x_start]);
      const y1 = num(p[g.y_start]);
      const x2 = num(p[g.x_end]);
      const y2 = num(p[g.y_end]);
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
      const xStart = num(p[g.x_start]);
      const yStart = num(p[g.y_start]);
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
      p[g.x] = Math.round(box.x);
      p[g.y] = Math.round(box.y);
      return;
    }
    if (g.square) {
      const size = Math.max(1, Math.round(Math.max(box.w, box.h)));
      p[g.size] = size;
      p[g.x] = Math.round(box.x);
      p[g.y] = Math.round(box.y);
      return;
    }
    // text / multiline
    if (mode === 'resize') {
      const lines = String(p[g.text] ?? '').split('\n').length;
      const size = Math.max(1, Math.round(box.h / (lines * LINE_HEIGHT)));
      p[g.size] = size;
    }
    p[g.x] = Math.round(box.x);
    p[g.y] = Math.round(box.y);
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

export function snapValue(value, enabled, step = 2) {
  if (!enabled) return Math.round(value);
  return Math.round(value / step) * step;
}
