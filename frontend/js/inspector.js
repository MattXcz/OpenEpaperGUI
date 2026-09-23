// Property inspector — builds editors dynamically from the backend schema.

import { state, setState, findNode, typeSpec, emit } from './state.js';
import { render } from './canvas.js';

let container;
let emptyState;

export function initInspector() {
  container = document.getElementById('inspector');
  emptyState = document.getElementById('inspector-empty');
  renderInspector();
}

export function renderInspector() {
  if (!container) return;
  const node = state.selection ? findNode(state.selection) : null;

  if (!node) {
    container.innerHTML = '';
    emptyState.style.display = '';
    return;
  }
  emptyState.style.display = 'none';

  if (node.kind === 'group') {
    container.innerHTML = '';
    container.appendChild(buildGroupInspector(node));
    return;
  }

  const spec = typeSpec(node.type);
  if (!spec) {
    container.innerHTML = '<p class="muted">Unknown element type.</p>';
    return;
  }

  container.innerHTML = '';
  container.appendChild(buildHeader(node, spec));

  const groups = new Map();
  for (const field of spec.fields) {
    const groupName = field.group || 'Properties';
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push(field);
  }

  for (const [groupName, fields] of groups) {
    const section = document.createElement('div');
    section.className = 'field-group';
    const title = document.createElement('div');
    title.className = 'field-group-title';
    title.textContent = groupName;
    section.appendChild(title);
    for (const field of fields) {
      section.appendChild(buildField(node, field));
    }
    container.appendChild(section);
  }
}

function buildHeader(node, spec) {
  const head = document.createElement('div');
  head.className = 'inspector-head';
  head.innerHTML = `
    <span class="type-badge">${escapeHtml(spec.label)}</span>
    <span class="el-name">${escapeHtml(node.type)}</span>
  `;
  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;gap:2px;';

  const dup = document.createElement('button');
  dup.className = 'btn-icon';
  dup.title = 'Duplicate';
  dup.setAttribute('aria-label', dup.title);
  dup.textContent = '⧉';
  dup.addEventListener('click', async () => {
    const { duplicateSelected } = await import('./canvas.js');
    duplicateSelected();
  });

  const del = document.createElement('button');
  del.className = 'btn-icon';
  del.title = 'Delete';
  del.setAttribute('aria-label', del.title);
  del.textContent = '🗑';
  del.addEventListener('click', async () => {
    const { deleteSelected } = await import('./canvas.js');
    deleteSelected();
  });

  actions.append(dup, del);
  head.appendChild(actions);
  return head;
}

function buildGroupInspector(node) {
  const wrap = document.createElement('div');
  wrap.innerHTML = `
    <div class="inspector-head">
      <span class="type-badge" style="background:rgba(255,184,77,.15);color:var(--warning);">Repeat group</span>
      <span class="el-name">${escapeHtml(node.name || 'group')}</span>
    </div>
    <p class="muted small">
      A repeat group wraps its children in a Jinja <code>{% for %}</code> loop.
      Use the loop variable (default <code>i</code>) inside any field, e.g.
      <code>{{ 15 + i*spacing }}</code>.
    </p>
  `;

  const section = document.createElement('div');
  section.className = 'field-group';
  section.innerHTML = '<div class="field-group-title">Loop</div>';

  section.appendChild(buildSimpleField('Name', 'text', node.name || '', (value) => {
    node.name = value;
  }));

  section.appendChild(buildSimpleField('Loop variable', 'text', node.repeat?.var || 'i', (value) => {
    node.repeat.var = value || 'i';
  }));

  // A whole number (0 allowed) or a Jinja expression such as
  // `forecast | length` / `{{ n }}`; the generator handles both.
  const iterations = buildSimpleField('Iterations', 'text', node.repeat?.count ?? 1, (value) => {
    const text = String(value).trim();
    if (text === '') node.repeat.count = 1;
    else if (/^\d+$/.test(text)) node.repeat.count = Number(text);
    else node.repeat.count = text;
  });
  const help = document.createElement('div');
  help.className = 'field-help';
  help.innerHTML = 'A number, or a Jinja expression such as <code>forecast | length</code>.';
  iterations.appendChild(help);
  section.appendChild(iterations);

  section.appendChild(buildSimpleField('Enabled', 'bool', node.repeat?.enabled !== false, (value) => {
    node.repeat.enabled = value;
  }));

  const preField = document.createElement('div');
  preField.className = 'field';
  preField.innerHTML = `
    <div class="field-label"><span>Pre-loop statements</span></div>
    <textarea class="input" rows="3" placeholder="offsets = [offset_0, offset_1, offset_2]">${escapeHtml((node.repeat?.pre || []).join('\n'))}</textarea>
    <div class="field-help">One <code>{% set %}</code> per line. The <code>{% set %}</code> wrapper is added automatically.</div>
  `;
  const textarea = preField.querySelector('textarea');
  textarea.addEventListener('input', () => {
    node.repeat.pre = textarea.value.split('\n').map((line) => line.trim()).filter(Boolean);
    markDirty();
  });
  section.appendChild(preField);

  wrap.appendChild(section);

  const hint = document.createElement('p');
  hint.className = 'muted small';
  hint.textContent = 'Drag elements from the palette onto the canvas, then move them into this group via the Layers tab.';
  wrap.appendChild(hint);

  return wrap;
}

function buildSimpleField(label, kind, value, onChange) {
  const field = document.createElement('div');
  field.className = 'field';
  const labelEl = document.createElement('div');
  labelEl.className = 'field-label';
  labelEl.innerHTML = `<span>${escapeHtml(label)}</span>`;
  field.appendChild(labelEl);

  if (kind === 'bool') {
    const row = document.createElement('label');
    row.className = 'checkbox-row';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.checked = Boolean(value);
    input.addEventListener('change', () => { onChange(input.checked); markDirty(); });
    row.append(input, document.createTextNode('enabled'));
    field.appendChild(row);
    return field;
  }

  const input = document.createElement('input');
  input.className = 'input';
  input.type = kind === 'number' ? 'number' : 'text';
  input.value = value ?? '';
  input.addEventListener('input', () => {
    onChange(kind === 'number' ? Number(input.value) : input.value);
    markDirty();
  });
  field.appendChild(input);
  return field;
}

// ---------------------------------------------------------------------------
// Schema-driven fields
// ---------------------------------------------------------------------------

function buildField(node, field) {
  const wrap = document.createElement('div');
  wrap.className = 'field';

  const label = document.createElement('div');
  label.className = 'field-label';
  const isTemplate = field.template && typeof node.props[field.key] === 'string'
    && /\{\{|\{%/.test(node.props[field.key]);
  label.innerHTML = `<span>${escapeHtml(field.label)}</span>${isTemplate ? '<span class="tpl-badge">jinja</span>' : ''}`;
  wrap.appendChild(label);

  const value = node.props[field.key];
  const setValue = (next) => {
    node.props[field.key] = next;
    markDirty();
    if (field.kind === 'number' || field.kind === 'points' || field.kind === 'select') {
      render();
    }
  };

  switch (field.kind) {
    case 'number':
      wrap.appendChild(numberInput(value, field, setValue));
      break;
    case 'text':
      wrap.appendChild(textInput(value, field, setValue));
      break;
    case 'textarea':
      wrap.appendChild(textareaInput(value, field, setValue));
      break;
    case 'color':
      wrap.appendChild(colorInput(value, field, setValue));
      break;
    case 'select':
      wrap.appendChild(selectInput(value, field, setValue));
      break;
    case 'bool':
      wrap.appendChild(boolInput(value, field, setValue));
      break;
    case 'points':
      wrap.appendChild(pointsInput(value, field, setValue));
      break;
    case 'iconlist':
      wrap.appendChild(iconListInput(value, field, setValue));
      break;
    case 'plotdata':
      wrap.appendChild(plotDataInput(value, field, setValue));
      break;
    case 'object':
      wrap.appendChild(objectInput(node, field));
      break;
    default:
      wrap.appendChild(textInput(value, field, setValue));
  }

  if (field.help) {
    const help = document.createElement('div');
    help.className = 'field-help';
    help.innerHTML = field.help;
    wrap.appendChild(help);
  }
  return wrap;
}

function numberInput(value, field, setValue) {
  const input = document.createElement('input');
  input.className = 'input';
  input.type = 'text';
  input.value = value ?? '';
  if (field.min != null) input.dataset.min = field.min;
  input.placeholder = field.default != null ? String(field.default) : '';
  input.addEventListener('input', () => {
    const raw = input.value.trim();
    if (raw === '') { setValue(null); return; }
    if (/^\{\{|\{%/.test(raw)) { setValue(raw); return; }
    const parsed = Number(raw);
    setValue(Number.isFinite(parsed) ? parsed : raw);
  });
  return input;
}

function textInput(value, field, setValue) {
  const input = document.createElement('input');
  input.className = 'input';
  input.type = 'text';
  input.value = value ?? '';
  input.addEventListener('input', () => setValue(input.value));
  return input;
}

function textareaInput(value, field, setValue) {
  const input = document.createElement('textarea');
  input.className = 'input';
  input.rows = 3;
  input.value = value ?? '';
  input.addEventListener('input', () => setValue(input.value));
  return input;
}

function colorInput(value, field, setValue) {
  const row = document.createElement('div');
  row.className = 'color-row';

  const swatch = document.createElement('div');
  swatch.className = 'color-swatch';
  const updateSwatch = () => {
    const v = value ?? '';
    if (!v) {
      swatch.classList.add('is-none');
      swatch.style.background = '';
    } else {
      swatch.classList.remove('is-none');
      swatch.style.background = resolveSwatch(v);
    }
  };

  const select = document.createElement('select');
  select.className = 'input';
  const options = [...(field.options || [])];
  if (field.allow_none) options.unshift('');
  for (const option of options) {
    const opt = document.createElement('option');
    opt.value = option;
    opt.textContent = option === '' ? '— none —' : option;
    select.appendChild(opt);
  }
  const custom = document.createElement('option');
  custom.value = '__custom__';
  custom.textContent = 'custom hex…';
  select.appendChild(custom);

  const isKnown = options.includes(value ?? '');
  select.value = isKnown ? (value ?? '') : '__custom__';

  const hex = document.createElement('input');
  hex.className = 'input';
  hex.type = 'text';
  hex.placeholder = '#RRGGBB';
  hex.value = isKnown ? '' : (value ?? '');
  hex.style.display = isKnown ? 'none' : '';

  select.addEventListener('change', () => {
    if (select.value === '__custom__') {
      hex.style.display = '';
      hex.focus();
      return;
    }
    hex.style.display = 'none';
    value = select.value;
    updateSwatch();
    setValue(select.value);
  });

  hex.addEventListener('input', () => {
    value = hex.value;
    updateSwatch();
    setValue(hex.value);
  });

  updateSwatch();
  row.append(swatch, select, hex);
  return row;
}

function resolveSwatch(value) {
  const map = {
    black: '#000', white: '#fff', red: '#e02020', yellow: '#e8c000', accent: '#e02020',
    half_black: '#808080', half_white: '#c0c0c0', half_red: '#f09090',
    half_yellow: '#f4e090', half_accent: '#f09090',
  };
  const key = String(value).toLowerCase();
  return map[key] || key;
}

function selectInput(value, field, setValue) {
  const select = document.createElement('select');
  select.className = 'input';
  for (const option of field.options || []) {
    const opt = document.createElement('option');
    opt.value = option;
    opt.textContent = option;
    select.appendChild(opt);
  }
  select.value = value ?? field.default ?? '';
  select.addEventListener('change', () => setValue(select.value));
  return select;
}

function boolInput(value, field, setValue) {
  const row = document.createElement('label');
  row.className = 'checkbox-row';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.checked = Boolean(value);
  input.addEventListener('change', () => setValue(input.checked));
  row.append(input, document.createTextNode(field.label));
  return row;
}

function pointsInput(value, field, setValue) {
  const wrap = document.createElement('div');
  wrap.className = 'points-editor';
  let points = Array.isArray(value) ? value.map((pt) => [Number(pt[0]), Number(pt[1])]) : [];

  const rebuild = () => {
    wrap.innerHTML = '';
    points.forEach((point, index) => {
      const row = document.createElement('div');
      row.className = 'points-row';
      const x = document.createElement('input');
      x.className = 'input';
      x.type = 'number';
      x.value = point[0];
      const y = document.createElement('input');
      y.className = 'input';
      y.type = 'number';
      y.value = point[1];
      const del = document.createElement('button');
      del.className = 'btn-icon';
      del.textContent = '✕';
      del.addEventListener('click', () => {
        points.splice(index, 1);
        setValue(points.map((pt) => [...pt]));
        rebuild();
      });
      x.addEventListener('input', () => {
        points[index][0] = Number(x.value);
        setValue(points.map((pt) => [...pt]));
      });
      y.addEventListener('input', () => {
        points[index][1] = Number(y.value);
        setValue(points.map((pt) => [...pt]));
      });
      row.append(x, y, del);
      wrap.appendChild(row);
    });

    const add = document.createElement('button');
    add.className = 'btn btn-ghost btn-sm';
    add.textContent = '+ point';
    add.addEventListener('click', () => {
      const last = points[points.length - 1] || [0, 0];
      points.push([last[0] + 20, last[1] + 20]);
      setValue(points.map((pt) => [...pt]));
      rebuild();
    });
    wrap.appendChild(add);
  };

  rebuild();
  return wrap;
}

function iconListInput(value, field, setValue) {
  const wrap = document.createElement('div');
  wrap.className = 'iconlist-editor';
  let icons = Array.isArray(value) ? [...value] : [];

  const rebuild = () => {
    wrap.innerHTML = '';
    icons.forEach((icon, index) => {
      const row = document.createElement('div');
      row.className = 'iconlist-row';
      const input = document.createElement('input');
      input.className = 'input';
      input.value = icon;
      input.placeholder = 'mdi:home';
      const del = document.createElement('button');
      del.className = 'btn-icon';
      del.textContent = '✕';
      input.addEventListener('input', () => {
        icons[index] = input.value;
        setValue([...icons]);
      });
      del.addEventListener('click', () => {
        icons.splice(index, 1);
        setValue([...icons]);
        rebuild();
      });
      row.append(input, del);
      wrap.appendChild(row);
    });

    const add = document.createElement('button');
    add.className = 'btn btn-ghost btn-sm';
    add.textContent = '+ icon';
    add.addEventListener('click', () => {
      icons.push('mdi:home');
      setValue([...icons]);
      rebuild();
    });
    wrap.appendChild(add);
  };

  rebuild();
  return wrap;
}

function plotDataInput(value, field, setValue) {
  const wrap = document.createElement('div');
  wrap.className = 'plotdata-editor';
  let entries = Array.isArray(value) ? value.map((e) => ({ ...e })) : [];

  const rebuild = () => {
    wrap.innerHTML = '';
    entries.forEach((entry, index) => {
      const row = document.createElement('div');
      row.className = 'plotdata-row';

      const entity = document.createElement('input');
      entity.className = 'input';
      entity.placeholder = 'sensor.temperature';
      entity.value = entry.entity || '';

      const color = document.createElement('select');
      color.className = 'input';
      for (const option of state.schema?.colors || []) {
        const opt = document.createElement('option');
        opt.value = option;
        opt.textContent = option;
        color.appendChild(opt);
      }
      color.value = entry.color || 'black';

      const width = document.createElement('input');
      width.className = 'input';
      width.type = 'number';
      width.min = '1';
      width.value = entry.width ?? 1;
      width.style.maxWidth = '64px';

      const del = document.createElement('button');
      del.className = 'btn-icon';
      del.textContent = '✕';

      entity.addEventListener('input', () => { entries[index].entity = entity.value; setValue(entries.map((e) => ({ ...e }))); });
      color.addEventListener('change', () => { entries[index].color = color.value; setValue(entries.map((e) => ({ ...e }))); });
      width.addEventListener('input', () => { entries[index].width = Number(width.value); setValue(entries.map((e) => ({ ...e }))); });
      del.addEventListener('click', () => {
        entries.splice(index, 1);
        setValue(entries.map((e) => ({ ...e })));
        rebuild();
      });

      row.append(entity, color, width, del);
      wrap.appendChild(row);
    });

    const add = document.createElement('button');
    add.className = 'btn btn-ghost btn-sm';
    add.textContent = '+ entity';
    add.addEventListener('click', () => {
      entries.push({ entity: 'sensor.temperature', color: 'black', width: 1 });
      setValue(entries.map((e) => ({ ...e })));
      rebuild();
    });
    wrap.appendChild(add);
  };

  rebuild();
  return wrap;
}

// A nested option object (plot axes / legends): `null` = off, otherwise a dict
// of sub-properties edited with the regular field editors.
function objectInput(node, field) {
  const box = document.createElement('div');
  box.className = 'object-editor';

  const row = document.createElement('label');
  row.className = 'checkbox-row';
  const toggle = document.createElement('input');
  toggle.type = 'checkbox';
  toggle.checked = isPlainObject(node.props[field.key]);
  row.append(toggle, document.createTextNode(`Show ${field.label.toLowerCase()}`));
  box.appendChild(row);

  const body = document.createElement('div');
  body.className = 'object-fields';
  box.appendChild(body);

  const paint = () => {
    body.innerHTML = '';
    const value = node.props[field.key];
    body.hidden = !isPlainObject(value);
    if (!isPlainObject(value)) return;
    // The sub-editors write straight into this dict through a stand-in node.
    const proxy = { props: value };
    for (const sub of field.fields || []) {
      if (!(sub.key in value)) value[sub.key] = sub.default ?? null;
      body.appendChild(buildField(proxy, sub));
    }
  };

  toggle.addEventListener('change', () => {
    node.props[field.key] = toggle.checked ? {} : null;
    paint();
    markDirty();
  });

  paint();
  return box;
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function markDirty() {
  setState({ dirty: true }, 'change');
  emit('inspector');
}

function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
