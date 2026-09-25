// Clipboard access that also works over plain HTTP.
//
// `navigator.clipboard` only exists in a secure context (HTTPS or localhost),
// and the editor is usually opened as http://<lan-ip>:8099. There the old
// hidden-textarea + execCommand route is the only one that works.

export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none;';
  document.body.appendChild(area);
  area.select();
  try {
    if (!document.execCommand('copy')) throw new Error('Copy command was rejected');
  } finally {
    area.remove();
  }
}
