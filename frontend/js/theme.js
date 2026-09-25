// Shared presentation constants used by the canvas renderer, the palette, the
// layer list and the inspector. Keeping them in one place means a new color or
// element type only has to be described once.

/** drawcustom font file to the CSS family declared in styles.css. */
const FONT_FAMILIES = {
  'ppb.ttf': 'OEPL ppb',
  'rbm.ttf': 'OEPL rbm',
};

/** CSS font-family for a drawcustom `font`; unknown files use the default. */
export function fontFamily(font) {
  return FONT_FAMILIES[font] || FONT_FAMILIES['ppb.ttf'];
}

/** Every family, so the canvas can wait for them before measuring text. */
export const FONT_FAMILY_NAMES = Object.values(FONT_FAMILIES);

/**
 * ESL color names to hex. `accent` maps to red because the canvas has to pick
 * one; the real tag decides at render time.
 */
export const COLOR_MAP = {
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

/** Single letter shortcuts accepted by drawcustom. */
const COLOR_SHORTCUTS = {
  b: '#000000',
  w: '#ffffff',
  r: '#e02020',
  y: '#e8c000',
  a: '#e02020',
};

const HEX_RE = /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i;

/**
 * Resolves any drawcustom color value to a CSS color.
 * Unknown names fall back so a typo still renders something visible.
 */
export function resolveColor(value, fallback = '#000000') {
  if (!value) return fallback;
  const key = String(value).toLowerCase();
  if (COLOR_MAP[key]) return COLOR_MAP[key];
  if (COLOR_SHORTCUTS[key]) return COLOR_SHORTCUTS[key];
  if (HEX_RE.test(key)) return key;
  return fallback;
}

/**
 * Resolves a color for a small swatch. Unlike `resolveColor` it returns an
 * unknown value unchanged so the swatch can still show whatever the user typed.
 */
export function resolveSwatch(value) {
  if (!value) return '';
  const key = String(value).toLowerCase();
  if (COLOR_MAP[key]) return COLOR_MAP[key];
  if (COLOR_SHORTCUTS[key]) return COLOR_SHORTCUTS[key];
  return key;
}

/**
 * Compact glyphs for the palette and the layer list. These are plain characters
 * rather than MDI icons so they keep working when the webfont is unavailable.
 */
export const TYPE_GLYPHS = {
  text: 'T',
  multiline: '≡',
  icon: '★',
  icon_sequence: '⋯',
  qrcode: '▦',
  dlimg: '🖼',
  line: '─',
  rectangle: '▭',
  rectangle_pattern: '▦',
  polygon: '⬟',
  circle: '○',
  ellipse: '⬭',
  arc: '◔',
  progress_bar: '▰',
  plot: '📈',
  debug_grid: '▩',
};

/** Glyph for an element type, with a per-type fallback. */
export function glyphFor(type, spec = null) {
  return TYPE_GLYPHS[type] || spec?.label?.[0] || '◆';
}
