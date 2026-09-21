// Renders element previews onto the canvas (design-time approximation).

import { boundsOf } from './geometry.js';
import { typeSpec } from './state.js';

const COLOR_MAP = {
  black: '#000000',
  white: '#ffffff',
  red: '#e02020',
  yellow: '#e8c000',
  accent: '#e02020',
  half_black: '#808080',
  half_white: '#c0c0c0',
  half_red: '#f09090',
  half_yellow: '#f4e090',
  half_accent: '#f09090',
};

// The MDI webfont glyphs are optional; when it is missing we fall back to a
// simple placeholder so the canvas still communicates the layout.
let mdiAvailable = null;
function checkMdi() {
  if (mdiAvailable !== null) return mdiAvailable;
  try {
    const probe = document.createElement('i');
    probe.className = 'mdi mdi-home';
    probe.style.cssText = 'position:absolute;left:-9999px;font-size:24px;';
    document.body.appendChild(probe);
    const family = getComputedStyle(probe).fontFamily || '';
    mdiAvailable = /material/i.test(family);
    probe.remove();
  } catch {
    mdiAvailable = false;
  }
  return mdiAvailable;
}

export function hasMdi() {
  return checkMdi();
}

function iconHtml(name, color, size) {
  const safe = escapeHtml(iconName(name));
  if (checkMdi()) {
    return `<i class="mdi mdi-${safe}" style="font-size:${size}px;color:${color};line-height:1;"></i>`;
  }
  return `<span title="${safe}" style="display:grid;place-items:center;width:100%;height:100%;
    font-family:var(--mono);font-size:${Math.max(8, size * 0.5)}px;color:${color};
    border:1px dashed currentColor;border-radius:3px;box-sizing:border-box;overflow:hidden;">${safe.slice(0, 3)}</span>`;
}

export function resolveColor(value, fallback = '#000000') {
  if (!value) return fallback;
  const key = String(value).toLowerCase();
  if (COLOR_MAP[key]) return COLOR_MAP[key];
  if (/^#[0-9a-f]{3}$/i.test(key) || /^#[0-9a-f]{6}$/i.test(key)) return key;
  if (key === 'b') return '#000000';
  if (key === 'w') return '#ffffff';
  if (key === 'r') return '#e02020';
  if (key === 'y') return '#e8c000';
  if (key === 'a') return '#e02020';
  return fallback;
}

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function stripColorMarkup(text) {
  return String(text ?? '').replace(/\[\/?[a-z_]+\]/gi, '');
}

function iconName(value) {
  return String(value ?? '').replace(/^mdi:/, '');
}

/**
 * Builds the inner HTML for an element preview.
 */
export function renderElementContent(node) {
  const spec = typeSpec(node.type);
  if (!spec) return '<div class="el-placeholder">?</div>';
  // `__resolvedProps` holds the preview values (loop variable pinned to its
  // first iteration); fall back to the raw props for static elements.
  const p = node.__resolvedProps || node.props || {};
  const g = spec.geometry || {};

  switch (node.type) {
    case 'text': {
      let text = String(p.value ?? '');
      if (p.parse_colors) text = stripColorMarkup(text);
      const color = resolveColor(p.color, '#000');
      const size = Number(p.size) || 20;
      const weight = p.stroke_width ? 'bold' : 'normal';
      return `<div class="el-text" style="font-size:${size}px;color:${color};font-weight:${weight};white-space:pre-wrap;">${escapeHtml(text)}</div>`;
    }

    case 'multiline': {
      const delimiter = p.delimiter || '|';
      let text = String(p.value ?? '');
      if (p.parse_colors) text = stripColorMarkup(text);
      const lines = text.split(delimiter);
      const color = resolveColor(p.color, '#000');
      const size = Number(p.size) || 20;
      const offset = Number(p.offset_y) || 20;
      const html = lines
        .map((line, index) => `<div style="position:absolute;top:${index * offset}px;left:0;white-space:pre;">${escapeHtml(line)}</div>`)
        .join('');
      return `<div class="el-text" style="font-size:${size}px;color:${color};position:relative;">${html}</div>`;
    }

    case 'icon': {
      const size = Number(p.size) || 24;
      const color = resolveColor(p.fill, '#000');
      return `<div class="el-icon">${iconHtml(p.value, color, size)}</div>`;
    }

    case 'icon_sequence': {
      const icons = Array.isArray(p.icons) ? p.icons : [];
      const size = Number(p.size) || 24;
      const spacing = p.spacing != null && p.spacing !== '' ? Number(p.spacing) : size / 4;
      const color = resolveColor(p.fill, '#000');
      const direction = p.direction || 'right';
      const vertical = direction === 'up' || direction === 'down';
      const flex = vertical ? 'column' : 'row';
      const reverse = direction === 'left' || direction === 'up';
      const items = (reverse ? [...icons].reverse() : icons)
        .map((icon) => `<div style="width:${size}px;height:${size}px;flex:0 0 auto;">${iconHtml(icon, color, size)}</div>`)
        .join('');
      return `<div style="display:flex;flex-direction:${flex};gap:${spacing}px;color:${color};align-items:center;justify-content:center;width:100%;height:100%;">${items}</div>`;
    }

    case 'qrcode': {
      const box = Number(p.boxsize) || 2;
      const border = Number(p.border) || 1;
      const modules = 29 + border * 2;
      const side = modules * box;
      const fg = resolveColor(p.color, '#000');
      const bg = resolveColor(p.bgcolor, '#fff');
      return `<div class="el-qr" style="width:${side}px;height:${side}px;background:${bg};color:${fg};">
        <div style="font-family:var(--mono);font-size:${Math.max(8, side / 6)}px;opacity:.75;">QR</div>
      </div>`;
    }

    case 'dlimg': {
      const url = String(p.url ?? '');
      if (/^https?:\/\//i.test(url)) {
        return `<img class="el-img" src="${escapeHtml(url)}" alt="" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'el-placeholder',textContent:'image'}))" />`;
      }
      return '<div class="el-placeholder">image</div>';
    }

    case 'line': {
      const color = resolveColor(p.fill, '#000');
      const width = Number(p.width) || 1;
      const dashed = p.dashed ? `stroke-dasharray="${Number(p.dash_length) || 5} ${Number(p.space_length) || 3}"` : '';
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <line x1="0" y1="0" x2="100" y2="100" stroke="${color}" stroke-width="${width}" ${dashed} vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'rectangle': {
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      const radius = Number(p.radius) || 0;
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <rect x="0" y="0" width="100" height="100" rx="${radius}" ry="${radius}"
          fill="${fill}" stroke="${outline}" stroke-width="${width}" vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'rectangle_pattern': {
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      const xRepeat = Math.max(1, Number(p.x_repeat) || 1);
      const yRepeat = Math.max(1, Number(p.y_repeat) || 1);
      const xSize = Number(p.x_size) || 10;
      const ySize = Number(p.y_size) || 10;
      const xOffset = Number(p.x_offset) || 0;
      const yOffset = Number(p.y_offset) || 0;
      const totalW = xRepeat * xSize + (xRepeat - 1) * xOffset;
      const totalH = yRepeat * ySize + (yRepeat - 1) * yOffset;
      let rects = '';
      for (let row = 0; row < yRepeat; row += 1) {
        for (let col = 0; col < xRepeat; col += 1) {
          const x = col * (xSize + xOffset);
          const y = row * (ySize + yOffset);
          rects += `<rect x="${x}" y="${y}" width="${xSize}" height="${ySize}" fill="${fill}" stroke="${outline}" stroke-width="${width}" />`;
        }
      }
      return `<svg class="el-shape" viewBox="0 0 ${totalW} ${totalH}" preserveAspectRatio="none">${rects}</svg>`;
    }

    case 'polygon': {
      const points = Array.isArray(p.points) ? p.points : [];
      const box = boundsOf(node) || { x: 0, y: 0, w: 1, h: 1 };
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      const pts = points
        .map((pt) => `${(Number(pt[0]) - box.x)},${(Number(pt[1]) - box.y)}`)
        .join(' ');
      return `<svg class="el-shape" viewBox="0 0 ${Math.max(1, box.w)} ${Math.max(1, box.h)}" preserveAspectRatio="none">
        <polygon points="${pts}" fill="${fill}" stroke="${outline}" stroke-width="${width}" vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'circle': {
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <circle cx="50" cy="50" r="49" fill="${fill}" stroke="${outline}" stroke-width="${width}" vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'ellipse': {
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <ellipse cx="50" cy="50" rx="49" ry="49" fill="${fill}" stroke="${outline}" stroke-width="${width}" vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'arc': {
      const start = Number(p.start_angle) || 0;
      const end = Number(p.end_angle) || 0;
      const fill = p.fill ? resolveColor(p.fill) : 'none';
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      const sweep = end - start;
      const largeArc = Math.abs(sweep) > 180 ? 1 : 0;
      const toRad = (deg) => (deg * Math.PI) / 180;
      const x1 = 50 + 49 * Math.cos(toRad(start));
      const y1 = 50 + 49 * Math.sin(toRad(start));
      const x2 = 50 + 49 * Math.cos(toRad(end));
      const y2 = 50 + 49 * Math.sin(toRad(end));
      const path = fill !== 'none'
        ? `M 50 50 L ${x1} ${y1} A 49 49 0 ${largeArc} 1 ${x2} ${y2} Z`
        : `M ${x1} ${y1} A 49 49 0 ${largeArc} 1 ${x2} ${y2}`;
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <path d="${path}" fill="${fill}" stroke="${outline}" stroke-width="${width}" vector-effect="non-scaling-stroke" />
      </svg>`;
    }

    case 'progress_bar': {
      const progress = Math.max(0, Math.min(100, Number(p.progress) || 0));
      const bg = resolveColor(p.background, '#fff');
      const fill = resolveColor(p.fill, '#e02020');
      const outline = resolveColor(p.outline, '#000');
      const width = Number(p.width) || 1;
      const direction = p.direction || 'right';
      const vertical = direction === 'up' || direction === 'down';
      const reverse = direction === 'left' || direction === 'up';
      const pct = reverse ? 100 - progress : progress;
      const fillStyle = vertical
        ? `height:${pct}%;width:100%;${reverse ? 'bottom:0;' : 'top:0;'}position:absolute;`
        : `width:${pct}%;height:100%;${reverse ? 'right:0;' : 'left:0;'}position:absolute;`;
      const label = p.show_percentage
        ? `<span style="position:absolute;inset:0;display:grid;place-items:center;font-family:var(--mono);font-size:${Math.max(8, (boundsOf(node)?.h || 20) * 0.6)}px;color:#000;">${progress}%</span>`
        : '';
      return `<div style="position:absolute;inset:0;background:${bg};border:${width}px solid ${outline};overflow:hidden;">
        <div style="${fillStyle}background:${fill};"></div>${label}
      </div>`;
    }

    case 'plot': {
      const entries = Array.isArray(p.data) ? p.data : [];
      const colors = entries.map((e) => resolveColor(e.color, '#000'));
      const paths = entries.map((entry, index) => {
        const color = colors[index];
        const width = Number(entry.width) || 1;
        const points = [];
        const steps = 24;
        for (let i = 0; i <= steps; i += 1) {
          const x = (i / steps) * 100;
          const y = 50 + 35 * Math.sin((i / steps) * Math.PI * 2 + index * 1.2);
          points.push(`${x},${y}`);
        }
        return `<polyline points="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="${width}" vector-effect="non-scaling-stroke" />`;
      }).join('');
      return `<svg class="el-shape" viewBox="0 0 100 100" preserveAspectRatio="none">
        <rect x="0" y="0" width="100" height="100" fill="none" stroke="#ccc" stroke-width="1" vector-effect="non-scaling-stroke" />
        ${paths}
      </svg>`;
    }

    case 'debug_grid': {
      return `<div style="position:absolute;inset:0;background-image:
        linear-gradient(to right, rgba(0,0,0,.25) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(0,0,0,.25) 1px, transparent 1px);
        background-size:${Number(p.spacing) || 20}px ${Number(p.spacing) || 20}px;"></div>`;
    }

    default:
      return `<div class="el-placeholder">${escapeHtml(node.type)}</div>`;
  }
}

export function elementLabel(node) {
  if (node.kind === 'group') return node.name || 'Repeat group';
  const spec = typeSpec(node.type);
  const p = node.props || {};
  let detail = '';
  if (node.type === 'text' || node.type === 'multiline') detail = String(p.value ?? '').slice(0, 22);
  else if (node.type === 'icon') detail = iconName(p.value);
  else if (node.type === 'qrcode') detail = String(p.data ?? '').slice(0, 18);
  else if (node.type === 'dlimg') detail = String(p.url ?? '').slice(0, 18);
  else if (node.type === 'plot') detail = `${(p.data || []).length} series`;
  return detail ? `${spec?.label || node.type}: ${detail}` : (spec?.label || node.type);
}
