(() => {
  if (window.SpanishHelper) return;
  let host, root, data, busy = new Set(), expanded = false, lastSelection = '';
  const speaker = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
  const bulb = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 2H9s0-1-1-2Z"/></svg>';
  const el = (id) => root.getElementById(id);
  function captureSelection() {
    const selection = window.getSelection();
    const qa = document.getElementById('qa');
    if (selection && qa && selection.rangeCount && qa.contains(selection.anchorNode) && qa.contains(selection.focusNode)) {
      const text = selection.toString().trim();
      if (text && text.length <= 180) lastSelection = text;
      else lastSelection = '';
    } else lastSelection = '';
  }
  function sync() {
    for (const action of ['pronounce', 'hint']) {
      el(action).disabled = busy.has(action);
      el(action).setAttribute('aria-busy', String(busy.has(action)));
    }
    el('hint').setAttribute('aria-expanded', String(expanded));
    el('hint-panel').hidden = !expanded;
    el('hint-label').textContent = busy.has('hint') ? 'Buscando…' : expanded ? 'Ocultar pista' : 'Dame una pista';
    el('pronounce-label').textContent = busy.has('pronounce') ? 'Preparando…' : 'Pronunciar';
  }
  function action(name) {
    if (busy.has(name)) return;
    if (name === 'hint' && expanded) { expanded = false; sync(); return; }
    captureSelection();
    busy.add(name);
    el('status').textContent = name === 'hint' ? 'Un momento, buscamos una pista…' : 'Preparando la pronunciación…';
    el('status').dataset.error = 'false';
    sync();
    const request = {token: data.token, action: name, selection: lastSelection, selectionOnCard: !!lastSelection};
    if (typeof window.pycmd === 'function') window.pycmd('spanish-helper:' + JSON.stringify(request));
    else receive({event: 'error', token: data.token, action: name, message: 'Abre esta tarjeta en Anki para usar el ayudante.'});
  }
  function destroy() {
    if (host) host.remove();
    const spacer = document.getElementById('spanish-helper-space');
    if (spacer) spacer.remove();
    host = null;
    if (window.__spanishHelperObserver) window.__spanishHelperObserver.disconnect();
  }
  function mount(next, css) {
    destroy(); data = next; busy.clear(); expanded = false; lastSelection = '';
    host = document.createElement('div'); host.id = 'spanish-helper';
    root = host.attachShadow({mode: 'open'});
    const style = document.createElement('style'); style.textContent = css; root.append(style);
    const panel = document.createElement('section');
    panel.className = 'helper'; panel.setAttribute('aria-label', 'Ayudante de español'); panel.lang = 'es';
    panel.innerHTML = '<header><span class="eyebrow"><i></i> TU COMPAÑERO DE ESPAÑOL</span><span class="level">B1</span></header>' +
      '<div class="heading"><span id="word"></span><span class="tagline">Una pequeña ayuda para seguir.</span></div>' +
      '<div class="actions"><button type="button" id="pronounce">' + speaker + '<span id="pronounce-label">Pronunciar</span><kbd>Alt P</kbd></button>' +
      '<button type="button" id="hint" aria-controls="hint-panel" aria-expanded="false">' + bulb + '<span id="hint-label">Dame una pista</span><kbd>Alt H</kbd></button></div>' +
      '<div id="hint-panel" hidden><div class="hint-kind" id="hint-kind">EN CONTEXTO</div><p id="example"></p><p id="explanation"></p><a id="source" target="_blank" rel="noopener noreferrer"></a></div>' +
      '<div id="status" role="status" aria-live="polite">Selecciona una palabra para practicar solo esa parte.</div>';
    root.append(panel); document.body.append(host);
    el('word').textContent = next.word || '¿Qué palabra practicamos?';
    for (const name of ['pronounce', 'hint']) {
      el(name).addEventListener('pointerdown', captureSelection);
      el(name).addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); action(name); });
    }
    const spacer = document.createElement('div'); spacer.id = 'spanish-helper-space'; spacer.setAttribute('aria-hidden', 'true'); document.body.append(spacer);
    window.__spanishHelperObserver = new ResizeObserver(() => { spacer.style.height = (panel.getBoundingClientRect().height + 42) + 'px'; });
    window.__spanishHelperObserver.observe(panel);
    // Match Anki's theme even when its own styles cannot cross the shadow boundary.
    host.dataset.dark = String(document.body.classList.contains('nightMode') || document.documentElement.classList.contains('night-mode'));
    sync();
  }
  function receive(message) {
    if (!host || message.token !== data.token) return;
    if (message.event === 'hint') {
      busy.delete('hint'); expanded = true;
      el('hint-kind').textContent = message.example ? 'EN CONTEXTO' : 'SIGNIFICADO';
      el('example').textContent = message.example || ''; el('example').hidden = !message.example;
      el('explanation').textContent = message.explanation || ''; el('explanation').hidden = !message.explanation;
      el('source').textContent = message.source || '';
      if (message.url && (message.url.startsWith('https://en.wiktionary.org/') || message.url.startsWith('https://es.wiktionary.org/'))) el('source').href = message.url;
      else el('source').removeAttribute('href');
      el('status').textContent = 'Piensa en el significado. Dale tiempo a tu memoria.';
    } else if (message.event === 'audio') {
      busy.delete('pronounce'); el('status').textContent = 'Escucha y repite: ' + message.word;
    } else if (message.event === 'error') {
      busy.delete(message.action); el('status').textContent = message.message; el('status').dataset.error = 'true';
    }
    sync();
  }
  document.addEventListener('selectionchange', () => { if (host) captureSelection(); });
  document.addEventListener('keydown', (event) => {
    if (!host || !event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    if (event.target.closest && event.target.closest('input,textarea,[contenteditable="true"]')) return;
    const name = {p: 'pronounce', h: 'hint'}[event.key.toLowerCase()];
    if (name) { event.preventDefault(); event.stopPropagation(); action(name); }
  });
  window.SpanishHelper = {mount, receive, destroy};
})();
