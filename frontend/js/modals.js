// Modal dialogs: projects, settings, export, push.

import { state, setState, createProject } from './state.js';
import { api } from './api.js';
import { PRESETS } from './presets.js';
import { copyText } from './clipboard.js';

const root = () => document.getElementById('modal-root');

export function toast(message, kind = 'info') {
  const host = document.getElementById('toast-root');
  const el = document.createElement('div');
  el.className = `toast${kind === 'error' ? ' is-error' : kind === 'success' ? ' is-success' : ''}`;
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

function openModal(title, bodyBuilder, footerBuilder) {
  const host = root();
  host.hidden = false;
  host.innerHTML = '';

  const modal = document.createElement('div');
  modal.className = 'modal';

  const head = document.createElement('div');
  head.className = 'modal-head';
  head.innerHTML = `<h3>${title}</h3>`;
  const close = document.createElement('button');
  close.className = 'btn-icon';
  close.textContent = '✕';
  close.addEventListener('click', closeModal);
  head.appendChild(close);

  const body = document.createElement('div');
  body.className = 'modal-body';
  bodyBuilder(body);

  const foot = document.createElement('div');
  foot.className = 'modal-foot';
  if (footerBuilder) footerBuilder(foot);

  modal.append(head, body, foot);
  host.appendChild(modal);

  host.onclick = (event) => { if (event.target === host) closeModal(); };
  return { modal, body, foot };
}

export function closeModal() {
  const host = root();
  host.hidden = true;
  host.innerHTML = '';
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------

export async function openProjects(onLoad) {
  let projects = [];
  try {
    projects = await api.listProjects();
  } catch (error) {
    toast(error.message, 'error');
  }

  openModal('Projects', (body) => {
    const templatesTitle = document.createElement('div');
    templatesTitle.className = 'field-group-title';
    templatesTitle.textContent = 'Start from a template';
    body.appendChild(templatesTitle);

    const templates = document.createElement('div');
    templates.className = 'project-list';
    for (const preset of PRESETS) {
      const item = document.createElement('div');
      item.className = 'project-item';
      item.innerHTML = `
        <span class="pi-name">${escapeHtml(preset.name)}<br><span class="pi-meta">${escapeHtml(preset.description)}</span></span>
      `;
      item.addEventListener('click', () => {
        onLoad(preset.build());
        closeModal();
        toast(`Created "${preset.name}"`, 'success');
      });
      templates.appendChild(item);
    }
    body.appendChild(templates);

    const savedTitle = document.createElement('div');
    savedTitle.className = 'field-group-title';
    savedTitle.style.marginTop = '18px';
    savedTitle.textContent = 'Saved projects';
    body.appendChild(savedTitle);

    const list = document.createElement('div');
    list.className = 'project-list';

    if (!projects.length) {
      list.innerHTML = '<p class="muted small">No saved projects yet.</p>';
    }

    for (const project of projects) {
      const item = document.createElement('div');
      item.className = 'project-item';
      item.innerHTML = `
        <span class="pi-name">${escapeHtml(project.name)}</span>
        <span class="pi-meta">${project.width}×${project.height}</span>
      `;
      const del = document.createElement('button');
      del.className = 'btn-icon';
      del.textContent = '🗑';
      del.title = `Delete ${project.name}`;
      del.setAttribute('aria-label', `Delete project ${project.name}`);
      del.addEventListener('click', async (event) => {
        event.stopPropagation();
        if (!window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) return;
        try {
          await api.deleteProject(project.id);
          item.remove();
          toast('Project deleted', 'success');
        } catch (error) {
          toast(error.message, 'error');
        }
      });
      item.appendChild(del);
      item.addEventListener('click', async () => {
        try {
          const full = await api.getProject(project.id);
          onLoad(full);
          closeModal();
          toast(`Loaded "${full.name}"`, 'success');
        } catch (error) {
          toast(error.message, 'error');
        }
      });
      list.appendChild(item);
    }
    body.appendChild(list);
  }, (foot) => {
    const newBtn = document.createElement('button');
    newBtn.className = 'btn btn-primary';
    newBtn.textContent = 'New blank project';
    newBtn.addEventListener('click', () => {
      onLoad(createProject('Untitled'));
      closeModal();
    });
    foot.appendChild(newBtn);
  });
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------

export async function openSettings(onSaved) {
  let settings = state.settings;
  try {
    settings = await api.getSettings();
  } catch { /* use cached */ }

  let status = { connected: false, message: 'not checked' };

  const { body } = openModal('Settings', (host) => {
    host.innerHTML = `
      <div class="field">
        <div class="field-label"><span>Home Assistant URL</span></div>
        <input id="set-url" class="input" type="text" placeholder="http://homeassistant.local:8123" value="${escapeHtml(settings.haUrl || '')}" />
      </div>
      <div class="field">
        <div class="field-label"><span>Long-lived access token</span></div>
        <input id="set-token" class="input" type="password" placeholder="${settings.hasToken ? '•••••••• (already set)' : 'paste token'}" />
        <div class="field-help">Leave empty to keep the existing token. Changing the URL requires entering the token again. Can also be provided via the <code>HA_TOKEN</code> environment variable (used only with <code>HA_URL</code>).</div>
      </div>
      <div class="field">
        <div class="field-label"><span>Target device ID</span></div>
        <input id="set-device" class="input" type="text" placeholder="e.g. 0011223344556677" value="${escapeHtml(settings.deviceId || '')}" />
        <div class="field-help">The OpenEPaperLink tag MAC / device id used by <code>drawcustom</code>.</div>
      </div>
      <div class="field">
        <div class="field-label"><span>Service</span></div>
        <input id="set-service" class="input" type="text" value="${escapeHtml(settings.service || 'open_epaper_link.drawcustom')}" />
      </div>
      <div class="field">
        <div class="field-label"><span>Connection</span></div>
        <div id="set-status" class="muted small">not checked</div>
      </div>
    `;
  }, (foot) => {
    const test = document.createElement('button');
    test.className = 'btn btn-ghost';
    test.textContent = 'Test connection';
    test.addEventListener('click', async () => {
      const statusEl = document.getElementById('set-status');
      statusEl.textContent = 'checking…';
      try {
        await save();
        const result = await api.haStatus();
        status = result;
        statusEl.textContent = result.connected ? `✅ ${result.message}` : `❌ ${result.message}`;
        statusEl.style.color = result.connected ? 'var(--success)' : 'var(--danger)';
      } catch (error) {
        statusEl.textContent = `❌ ${error.message}`;
        statusEl.style.color = 'var(--danger)';
      }
    });

    const saveBtn = document.createElement('button');
    saveBtn.className = 'btn btn-primary';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', async () => {
      await save();
      closeModal();
      toast('Settings saved', 'success');
      if (onSaved) onSaved();
    });

    foot.append(test, saveBtn);
  });

  async function save() {
    const payload = {
      haUrl: document.getElementById('set-url').value.trim(),
      deviceId: document.getElementById('set-device').value.trim(),
      service: document.getElementById('set-service').value.trim(),
    };
    const token = document.getElementById('set-token').value.trim();
    if (token) payload.haToken = token;
    const saved = await api.saveSettings(payload);
    setState({ settings: saved });
    if (saved.tokenCleared) {
      // The token is bound to the URL it was entered for (see storage.py).
      toast('Home Assistant URL changed — please enter the token for the new URL', 'error');
      document.getElementById('set-token').placeholder = 'paste token';
    }
    return saved;
  }
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

export function openExport() {
  const template = state.generated.template || '';
  const yaml = state.generated.yaml || '';
  const payload = JSON.stringify(state.generated.payload || [], null, 2);

  openModal('Export', (body) => {
    body.innerHTML = `
      <p class="muted small">Paste the Jinja template into a Home Assistant script, automation or template sensor.</p>
      <div class="code-switch">
        <button class="chip is-active" data-exp="template">Jinja</button>
        <button class="chip" data-exp="yaml">YAML</button>
        <button class="chip" data-exp="payload">JSON</button>
      </div>
      <pre id="exp-out" class="code-output" style="max-height:44vh;"></pre>
    `;
    const out = body.querySelector('#exp-out');
    const values = { template, yaml, payload };
    out.textContent = template;
    body.querySelectorAll('[data-exp]').forEach((button) => {
      button.addEventListener('click', () => {
        body.querySelectorAll('[data-exp]').forEach((b) => b.classList.remove('is-active'));
        button.classList.add('is-active');
        out.textContent = values[button.dataset.exp];
      });
    });
  }, (foot) => {
    const download = document.createElement('button');
    download.className = 'btn btn-ghost';
    download.textContent = 'Download .jinja';
    download.addEventListener('click', () => {
      const blob = new Blob([template], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(state.project.name || 'epaper').replace(/\s+/g, '-').toLowerCase()}.jinja`;
      link.click();
      URL.revokeObjectURL(url);
    });

    const copy = document.createElement('button');
    copy.className = 'btn btn-primary';
    copy.textContent = 'Copy template';
    copy.addEventListener('click', async () => {
      try {
        await copyText(template);
        toast('Template copied', 'success');
      } catch {
        toast('Copy failed — use Download instead', 'error');
      }
    });

    foot.append(download, copy);
  });
}

// ---------------------------------------------------------------------------
// Import from code
// ---------------------------------------------------------------------------

/**
 * Paste a JSON payload, service data or a Jinja template. `onImport` gets the
 * parsed result and whether to replace the current elements.
 */
export function openImport(onImport) {
  let area;
  let replace;
  let errorEl;

  openModal('Import from code', (body) => {
    body.innerHTML = `
      <p class="muted small">Paste a <code>drawcustom</code> payload: a JSON list of elements,
        service data with a <code>payload</code> key, or a Jinja template.
        <code>{% set %}</code> becomes a variable and <code>{% for i in range(n) %}</code> a repeat group.</p>
      <textarea id="import-code" class="input" rows="14" spellcheck="false"
        placeholder='[{"type": "text", "value": "Hello", "x": 10, "y": 10, "size": 20}]'></textarea>
      <label class="checkbox-row" style="margin-top:10px;"><input id="import-replace" type="checkbox" /> Replace current elements and variables</label>
      <div id="import-error" class="code-status is-error" role="alert" style="margin-top:10px;" hidden></div>
    `;
    area = body.querySelector('#import-code');
    replace = body.querySelector('#import-replace');
    errorEl = body.querySelector('#import-error');
    setTimeout(() => area.focus(), 0);
  }, (foot) => {
    const cancel = document.createElement('button');
    cancel.className = 'btn btn-ghost';
    cancel.textContent = 'Cancel';
    cancel.addEventListener('click', closeModal);

    const submit = document.createElement('button');
    submit.className = 'btn btn-primary';
    submit.textContent = 'Import';
    submit.addEventListener('click', async () => {
      submit.disabled = true;
      errorEl.hidden = true;
      try {
        const result = await api.importCode(area.value);
        onImport(result, replace.checked);
        closeModal();
        const count = result.nodes.length;
        toast(`Imported ${count} item${count === 1 ? '' : 's'}`, 'success');
        for (const warning of result.warnings) toast(warning);
      } catch (error) {
        errorEl.textContent = `✕ ${error.message}`;
        errorEl.hidden = false;
      } finally {
        submit.disabled = false;
      }
    });

    foot.append(cancel, submit);
  });
}

// ---------------------------------------------------------------------------
// Pixel-accurate preview
// ---------------------------------------------------------------------------

/**
 * Renders the project with the real drawing code and shows the PNG.
 *
 * This is the honest counterpart to the canvas: same fonts, colours,
 * coordinates and Pillow calls as the integration, so what is shown here is
 * what the tag will draw.
 */
export async function openPixelPreview() {
  let result = null;
  let failure = null;

  try {
    result = await api.preview(state.project, state.previewAccent || 'red');
  } catch (error) {
    failure = error.message;
  }

  let zoom = 2;
  let showGrid = false;

  openModal('Pixel preview', (body) => {
    if (failure) {
      body.innerHTML = `<div class="preview-error">${escapeHtml(failure)}</div>`;
      return;
    }

    const wrap = document.createElement('div');
    wrap.className = 'preview-wrap';

    const toolbar = document.createElement('div');
    toolbar.className = 'preview-toolbar';
    toolbar.innerHTML = `
      <span class="muted small">${result.width}×${result.height} · ${result.elements} element(s)</span>
      <span class="preview-spacer"></span>
      <label class="field-inline"><span>Accent</span>
        <select id="preview-accent" class="input input-sm">
          <option value="red">red</option>
          <option value="yellow">yellow</option>
        </select>
      </label>
      <label class="field-inline"><span>Zoom</span>
        <input id="preview-zoom" class="input input-sm input-num" type="number" min="1" max="8" step="1" value="${zoom}" />
      </label>
      <button id="preview-checker" class="btn btn-ghost btn-sm">▦ Checkerboard</button>
    `;
    wrap.appendChild(toolbar);

    const stage = document.createElement('div');
    stage.className = 'preview-stage';

    const img = document.createElement('img');
    img.className = 'preview-image';
    img.src = result.image;
    img.alt = 'Rendered preview of the display';
    stage.appendChild(img);
    wrap.appendChild(stage);

    const applyZoom = () => {
      img.style.width = `${result.width * zoom}px`;
      img.style.height = `${result.height * zoom}px`;
      img.style.imageRendering = zoom >= 2 ? 'pixelated' : 'auto';
    };
    applyZoom();

    const zoomInput = toolbar.querySelector('#preview-zoom');
    zoomInput.addEventListener('input', () => {
      zoom = Math.min(8, Math.max(1, Number(zoomInput.value) || 1));
      applyZoom();
    });

    const accentSelect = toolbar.querySelector('#preview-accent');
    accentSelect.value = state.previewAccent || 'red';
    accentSelect.addEventListener('change', async () => {
      setState({ previewAccent: accentSelect.value });
      closeModal();
      await openPixelPreview();
    });

    toolbar.querySelector('#preview-checker').addEventListener('click', (event) => {
      showGrid = !showGrid;
      stage.classList.toggle('is-checkered', showGrid);
      event.target.classList.toggle('is-active', showGrid);
    });

    body.appendChild(wrap);

    if (result.errors.length) {
      body.appendChild(previewIssues('✕ Some elements could not be drawn', result.errors, 'is-error'));
    }
    if (result.notes.length) {
      body.appendChild(previewIssues('ℹ Not shown in this preview', result.notes, 'is-note'));
    }
  }, (foot) => {
    const download = document.createElement('button');
    download.className = 'btn btn-ghost';
    download.textContent = 'Download PNG';
    download.addEventListener('click', () => {
      if (!result) return;
      const link = document.createElement('a');
      link.href = result.image;
      link.download = `${(state.project.name || 'epaper').replace(/\s+/g, '-').toLowerCase()}-preview.png`;
      link.click();
    });
    foot.appendChild(download);
  });
}

function previewIssues(title, items, className) {
  const box = document.createElement('div');
  box.className = `preview-issues ${className}`;
  const heading = document.createElement('div');
  heading.className = 'status-head';
  heading.textContent = title;
  box.appendChild(heading);
  const list = document.createElement('ul');
  for (const item of items) {
    const li = document.createElement('li');
    li.textContent = item;
    list.appendChild(li);
  }
  box.appendChild(list);
  return box;
}

// ---------------------------------------------------------------------------
// Push to display
// ---------------------------------------------------------------------------

export function openPush() {
  openModal('Send to display', (body) => {
    body.innerHTML = `
      <div class="field">
        <div class="field-label"><span>Device ID</span></div>
        <input id="push-device" class="input" type="text" value="${escapeHtml(state.settings.deviceId || '')}" placeholder="0011223344556677" />
      </div>
      <div class="field">
        <div class="field-label"><span>Service</span></div>
        <input id="push-service" class="input" type="text" value="${escapeHtml(state.settings.service || 'open_epaper_link.drawcustom')}" />
      </div>
      <div class="field-row">
        <div class="field">
          <div class="field-label"><span>Rotate</span></div>
          <select id="push-rotate" class="input">
            ${[0, 90, 180, 270].map((v) => `<option value="${v}"${state.project.rotate === v ? ' selected' : ''}>${v}°</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <div class="field-label"><span>Dither</span></div>
          <select id="push-dither" class="input">
            ${[[0, 'none'], [1, 'Floyd-Steinberg'], [2, 'ordered']].map(([v, label]) => `<option value="${v}"${state.project.dither === v ? ' selected' : ''}>${v} – ${label}</option>`).join('')}
          </select>
        </div>
        <div class="field">
          <div class="field-label"><span>TTL (s)</span></div>
          <input id="push-ttl" class="input" type="number" min="0" max="86400" value="${Number(state.project.ttl ?? 60)}" />
        </div>
      </div>
      <div class="field">
        <label class="checkbox-row"><input id="push-dry" type="checkbox" /> Dry run (render without sending)</label>
      </div>
      <p class="muted small">The generated Jinja template is sent as the <code>payload</code> parameter.
        Rotate, dither and TTL are saved with the project.</p>
    `;
    // The body is not in the document yet, so query it directly.
    const saveOptions = () => {
      const ttl = Math.round(Number(body.querySelector('#push-ttl').value));
      state.project.rotate = Number(body.querySelector('#push-rotate').value);
      state.project.dither = Number(body.querySelector('#push-dither').value);
      state.project.ttl = Number.isFinite(ttl) ? Math.min(86400, Math.max(0, ttl)) : 60;
      setState({ dirty: true }, 'change');
    };
    ['#push-rotate', '#push-dither', '#push-ttl'].forEach((selector) => {
      body.querySelector(selector).addEventListener('change', saveOptions);
    });
  }, (foot) => {
    const send = document.createElement('button');
    send.className = 'btn btn-primary';
    send.textContent = 'Send';
    send.addEventListener('click', async () => {
      send.disabled = true;
      send.textContent = 'Sending…';
      try {
        // Make sure a TTL that is still being typed is applied.
        document.getElementById('push-ttl').dispatchEvent(new Event('change'));
        const result = await api.haPush({
          project: state.project,
          deviceId: document.getElementById('push-device').value.trim(),
          service: document.getElementById('push-service').value.trim(),
          dryRun: document.getElementById('push-dry').checked,
        });
        toast(`Sent to ${result.deviceId}`, 'success');
        closeModal();
      } catch (error) {
        toast(error.message, 'error');
        send.disabled = false;
        send.textContent = 'Send';
      }
    });
    foot.appendChild(send);
  });
}

function escapeHtml(text) {
  return String(text ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
