(() => {
  if (window.SpanishHelper) return;
  let host, root, data, busy = new Set(), activePanel = '', lastSelection = '';
  let sizeObserver, themeObserver, checkResult = null, hintExample = '', pendingQuestion = '', pendingBubble = null;
  const icon = paths => '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths + '</svg>';
  const speaker = icon('<path d="M11 5 6 9H3v6h3l5 4V5Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>');
  const bulb = icon('<path d="M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 2H9s0-1-1-2Z"/>');
  const check = icon('<path d="M9 12l2 2 4-4"/><path d="M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z"/>');
  const close = icon('<path d="m6 6 12 12M6 18 18 6"/>');
  const chat = icon('<path d="M21 11a8 8 0 0 1-8 8H7l-5 3 2-6a8 8 0 1 1 17-5Z"/><path d="M8 10h8m-8 4h5"/>');
  const presets = [
    ['Meaning & usage', 'What does this Spanish word or expression mean, and how is it used?'],
    ['Translation', 'Is my saved translation accurate? Explain nuances and useful alternatives.'],
    ['Grammar', 'Explain the grammar of this word or phrase, including gender, agreement and sentence structure where relevant.'],
    ['Tenses & conjugation', 'If this word or phrase contains a verb, explain its tense and mood and show useful conjugations. Otherwise, explain how to use it with verbs.'],
    ['More examples', 'Give me three short B1 Spanish examples with English explanations.'],
  ];
  const el = id => root.getElementById(id);
  function captureSelection() {
    const selection = window.getSelection();
    const qa = document.getElementById('qa');
    if (selection && qa && selection.rangeCount && qa.contains(selection.anchorNode) && qa.contains(selection.focusNode)) {
      const text = selection.toString().trim();
      lastSelection = text && text.length <= 180 ? text : '';
    } else lastSelection = '';
  }
  function sync() {
    const audioBusy = busy.has('pronounce') || busy.has('example_audio');
    for (const name of ['pronounce', 'example_audio', 'hint', 'check']) {
      el(name).disabled = busy.has(name) || (['pronounce', 'example_audio'].includes(name) && audioBusy) || (name === 'check' && !data.answerShown);
      el(name).setAttribute('aria-busy', String(busy.has(name)));
    }
    for (const name of ['hint', 'check', 'chat']) {
      el(name).setAttribute('aria-expanded', String(activePanel === name));
      el(name + '-panel').hidden = activePanel !== name;
    }
    el('hint-label').textContent = busy.has('hint') ? 'Buscando…' : 'Pista';
    el('pronounce-label').textContent = busy.has('pronounce') ? 'Cargando…' : 'Pronunciar';
    el('check-label').textContent = busy.has('check') ? 'Comprobando…' : 'Comprobar';
    const chatting = busy.has('chat');
    el('chat-question').disabled = chatting;
    el('chat-send').disabled = chatting || !el('chat-question').value.trim();
    el('chat-send').textContent = chatting ? 'Thinking…' : 'Send';
    el('chat-form').setAttribute('aria-busy', String(chatting));
    for (const button of root.querySelectorAll('.preset')) button.disabled = chatting || (button.dataset.translation === 'true' && !data.answerShown);
  }
  function action(name) {
    if (name === 'chat') {
      activePanel = activePanel === 'chat' ? '' : 'chat'; sync();
      if (activePanel === 'chat') el('chat-question').focus();
      return;
    }
    if (busy.has(name) || (name === 'check' && !data.answerShown)) return;
    if (['pronounce', 'example_audio'].includes(name) && (busy.has('pronounce') || busy.has('example_audio'))) return;
    if (name === 'example_audio' && !hintExample) return;
    if (['hint', 'check'].includes(name) && activePanel === name) { activePanel = ''; sync(); return; }
    // Reopening a completed check does not perform another paid request.
    if (name === 'check' && checkResult) {
      activePanel = name; el('status').textContent = ''; sync(); return;
    }
    if (!['check', 'example_audio'].includes(name)) captureSelection();
    if (name === 'hint') {
      hintExample = ''; busy.delete('example_audio'); el('example-row').hidden = true;
    }
    busy.add(name);
    el('status').textContent = {hint: 'Buscando una pista…', pronounce: 'Preparando la pronunciación…', example_audio: 'Preparando el audio del ejemplo…', check: 'Revisando tu traducción…'}[name];
    el('status').dataset.error = 'false';
    sync();
    const useSelection = !['check', 'example_audio'].includes(name);
    const request = {token: data.token, action: name, selection: useSelection ? lastSelection : '', selectionOnCard: useSelection && !!lastSelection};
    if (typeof window.pycmd === 'function') window.pycmd('spanish-helper:' + JSON.stringify(request));
    else receive({event: 'error', token: data.token, action: name, message: 'Abre esta tarjeta en Anki para usar el ayudante.'});
  }
  function addChatMessage(role, text) {
    const item = document.createElement('div'); item.className = 'chat-message ' + role;
    const label = document.createElement('span'); label.className = 'chat-speaker';
    label.textContent = role === 'user' ? 'You' : 'AI tutor';
    const body = document.createElement('div'); body.className = 'chat-text';
    // Render common model emphasis using DOM nodes; never interpret answer HTML.
    for (const segment of text.split(/(\*\*[^*\n]+\*\*)/g)) {
      if (segment.startsWith('**') && segment.endsWith('**') && segment.length > 4) {
        const strong = document.createElement('strong'); strong.textContent = segment.slice(2, -2); body.append(strong);
      } else body.append(document.createTextNode(segment));
    }
    item.append(label, body); el('chat-messages').append(item);
    el('chat-empty').hidden = true;
    el('chat-messages').scrollTop = el('chat-messages').scrollHeight;
    return item;
  }
  function askQuestion(question) {
    if (busy.has('chat')) return;
    question = question.trim();
    if (!question || question.length > 1500) return;
    pendingQuestion = question;
    pendingBubble = addChatMessage('user', question);
    pendingBubble.classList.add('pending');
    el('chat-question').value = ''; el('chat-error').textContent = '';
    busy.add('chat'); sync();
    if (typeof window.pycmd === 'function') window.pycmd('spanish-helper:' + JSON.stringify({token: data.token, action: 'chat', question}));
    else receive({event:'error',token:data.token,action:'chat',message:'Open this card in Anki and connect ChatGPT to ask a question.'});
  }
  function destroy() {
    if (sizeObserver) sizeObserver.disconnect();
    if (themeObserver) themeObserver.disconnect();
    if (host) host.remove();
    const spacer = document.getElementById('spanish-helper-space');
    if (spacer) spacer.remove();
    host = null;
  }
  function mount(next, css) {
    destroy(); data = next; busy.clear(); activePanel = ''; lastSelection = ''; checkResult = null; hintExample = ''; pendingQuestion = ''; pendingBubble = null;
    host = document.createElement('div'); host.id = 'spanish-helper';
    root = host.attachShadow({mode: 'open'});
    const style = document.createElement('style'); style.textContent = css; root.append(style);
    const panel = document.createElement('section');
    panel.className = 'helper'; panel.setAttribute('aria-label', 'Ayudante de español'); panel.lang = 'es';
    panel.innerHTML = '<div id="hint-panel" class="result" role="region" aria-labelledby="hint-title" hidden>' +
      '<div class="result-header"><span class="result-title" id="hint-title">Pista</span><button class="close" type="button" aria-label="Cerrar pista">' + close + '</button></div>' +
      '<div class="example-row" id="example-row" hidden><p id="example"></p><button type="button" class="example-audio" id="example_audio" aria-label="Escuchar ejemplo" title="Escuchar el ejemplo completo">' + speaker + '</button></div>' +
      '<p id="explanation"></p><a class="source" id="source" target="_blank" rel="noopener noreferrer"></a></div>' +
      '<div id="check-panel" class="result" role="region" aria-labelledby="check-verdict" hidden>' +
      '<div class="result-header"><span class="result-title verdict" id="check-verdict"></span><button class="close" type="button" aria-label="Cerrar comprobación">' + close + '</button></div>' +
      '<div class="saved"><span class="field-label">Tu traducción guardada</span><span id="check-saved"></span></div><p id="check-explanation"></p>' +
      '<div class="suggestion" id="suggestion"><span class="field-label">Propuesta</span><span id="check-suggestion"></span></div>' +
      '<span class="source" id="check-source"></span><p class="note">La IA puede equivocarse. Tu tarjeta no se modifica.</p></div>' +
      '<div id="chat-panel" class="result chat-panel" lang="en" role="region" aria-labelledby="chat-title" hidden>' +
      '<div class="result-header"><span class="result-title" id="chat-title">Ask AI about this card</span><button class="close" type="button" aria-label="Close AI chat">' + close + '</button></div>' +
      '<p class="chat-context" id="chat-context"></p><p class="note" id="chat-scope"></p>' +
      '<div class="presets" id="chat-presets" role="group" aria-label="Suggested questions"></div>' +
      '<p class="chat-empty" id="chat-empty">Choose a question above or ask your own. You can ask follow-up questions too.</p>' +
      '<div id="chat-messages" class="chat-messages" role="log" aria-label="Conversation" aria-live="polite" aria-relevant="additions"></div>' +
      '<p id="chat-error" role="alert"></p><form id="chat-form" class="chat-form">' +
      '<label for="chat-question">Your question</label><div class="chat-composer"><textarea id="chat-question" rows="2" maxlength="1500" placeholder="Ask about meaning, translation, grammar or tenses…"></textarea><button id="chat-send" type="submit">Send</button></div>' +
      '<p class="note">Enter to send · Shift+Enter for a new line. Uses your ChatGPT plan. AI can make mistakes. Chat resets on a new card or side.</p></form></div>' +
      '<div class="actions" role="group" aria-label="Herramientas de español">' +
      '<button type="button" id="pronounce" title="Pronunciar la palabra o selección (Alt+P)" aria-label="Pronunciar" aria-keyshortcuts="Alt+P">' + speaker + '<span id="pronounce-label">Pronunciar</span><kbd aria-hidden="true">Alt P</kbd></button>' +
      '<button type="button" id="hint" aria-label="Pista" title="Mostrar una pista (Alt+H)" aria-keyshortcuts="Alt+H" aria-controls="hint-panel" aria-expanded="false">' + bulb + '<span id="hint-label">Pista</span><kbd aria-hidden="true">Alt H</kbd></button>' +
      '<button type="button" id="check" aria-label="Comprobar traducción" aria-keyshortcuts="Alt+C" aria-controls="check-panel" aria-expanded="false">' + check + '<span id="check-label">Comprobar</span><kbd aria-hidden="true">Alt C</kbd></button>' +
      '<button type="button" id="chat" lang="en" aria-label="Ask AI about this card" title="Ask about this card (Alt+A)" aria-keyshortcuts="Alt+A" aria-controls="chat-panel" aria-expanded="false">' + chat + '<span>Ask AI</span><kbd aria-hidden="true">Alt A</kbd></button></div>' +
      '<div class="plan-usage" id="plan-usage" hidden>Using ChatGPT plan · <a href="https://chatgpt.com/settings/usage" target="_blank" rel="noopener noreferrer">Manage usage</a></div>' +
      '<div id="status" role="status" aria-live="polite" aria-atomic="true"></div>';
    root.append(panel); document.body.append(host);
    el('plan-usage').hidden = !next.usingChatGPT;
    el('chat-context').textContent = next.word + (next.answerShown && next.meaning ? ' · ' + next.meaning : '');
    el('chat-scope').textContent = next.answerShown ? 'Questions include the saved translation and card example, when available.' : 'Reveal the answer to discuss your saved translation. For now, only the Spanish word is shared.';
    for (const [label, question] of presets) {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'preset';
      button.textContent = label; button.dataset.translation = String(label === 'Translation');
      button.title = label === 'Translation' && !next.answerShown ? 'Reveal the answer first' : question;
      button.addEventListener('click', () => askQuestion(question)); el('chat-presets').append(button);
    }
    el('chat-form').addEventListener('submit', event => { event.preventDefault(); event.stopPropagation(); askQuestion(el('chat-question').value); });
    el('chat-question').addEventListener('input', sync);
    el('chat-question').addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); askQuestion(event.currentTarget.value); }
    });
    // Keep review shortcuts from grading a card while typing in the chat.
    for (const kind of ['keyup', 'keypress']) el('chat-question').addEventListener(kind, event => event.stopPropagation());
    el('check').title = next.answerShown ? 'Revisar tu traducción guardada con IA (Alt+C)' : 'Muestra primero la respuesta para comprobar tu traducción';
    for (const name of ['pronounce', 'example_audio', 'hint', 'check', 'chat']) {
      el(name).addEventListener('pointerdown', captureSelection);
      el(name).addEventListener('click', event => { event.preventDefault(); event.stopPropagation(); action(name); });
    }
    for (const button of root.querySelectorAll('.close')) button.addEventListener('click', event => {
      event.preventDefault(); event.stopPropagation();
      const returnFocus = activePanel; activePanel = ''; sync();
      if (returnFocus) el(returnFocus).focus();
    });
    // The toolbar occupies only the review webview; Anki's answer/rating bar is separate.
    const spacer = document.createElement('div'); spacer.id = 'spanish-helper-space'; spacer.setAttribute('aria-hidden', 'true'); document.body.append(spacer);
    sizeObserver = new ResizeObserver(() => { spacer.style.height = (host.getBoundingClientRect().height + 12) + 'px'; });
    sizeObserver.observe(host);
    const matchTheme = () => {
      host.dataset.dark = String(document.body.classList.contains('nightMode') || document.documentElement.classList.contains('night-mode'));
      host.dataset.fancy = String(document.body.classList.contains('fancy'));
    };
    themeObserver = new MutationObserver(matchTheme);
    for (const element of [document.body, document.documentElement]) themeObserver.observe(element, {attributes:true, attributeFilter:['class']});
    matchTheme(); sync();
  }
  function receive(message) {
    if (!host || message.token !== data.token) return;
    if (message.event === 'hint') {
      busy.delete('hint'); if (activePanel !== 'chat') activePanel = 'hint';
      hintExample = (message.example || '').trim();
      el('hint-title').textContent = message.example ? 'En contexto' : 'Significado';
      el('example').textContent = hintExample; el('example-row').hidden = !hintExample;
      el('explanation').textContent = message.explanation || ''; el('explanation').hidden = !message.explanation;
      el('source').textContent = message.source || '';
      if (message.url && (message.url.startsWith('https://en.wiktionary.org/') || message.url.startsWith('https://es.wiktionary.org/'))) el('source').href = message.url;
      else el('source').removeAttribute('href');
      el('status').textContent = ''; el('status').dataset.error = 'false';
    } else if (message.event === 'check') {
      busy.delete('check'); if (activePanel !== 'chat') activePanel = 'check'; checkResult = message;
      el('check-verdict').textContent = {correct:'Parece correcta', partial:'Necesita un matiz', incorrect:'Posible error', uncertain:'No concluyente'}[message.verdict] || 'No concluyente';
      el('check-verdict').dataset.verdict = message.verdict;
      el('check-saved').textContent = message.saved || '';
      el('check-explanation').textContent = message.explanation || '';
      el('check-suggestion').textContent = message.suggestion || '';
      el('suggestion').hidden = !message.suggestion;
      el('check-source').textContent = message.source || '';
      el('status').textContent = ''; el('status').dataset.error = 'false';
    } else if (message.event === 'chat') {
      busy.delete('chat');
      if (pendingBubble) pendingBubble.classList.remove('pending');
      pendingBubble = null; pendingQuestion = '';
      addChatMessage('assistant', message.reply || '');
      el('chat-error').textContent = '';
    } else if (message.event === 'audio') {
      busy.delete(message.action || 'pronounce'); el('status').textContent = ''; el('status').dataset.error = 'false';
    } else if (message.event === 'error') {
      busy.delete(message.action);
      if (message.action === 'chat') {
        if (pendingBubble) pendingBubble.remove();
        pendingBubble = null; el('chat-question').value = pendingQuestion; pendingQuestion = '';
        el('chat-error').textContent = message.message;
        el('chat-empty').hidden = el('chat-messages').children.length > 0;
      } else { el('status').textContent = message.message; el('status').dataset.error = 'true'; }
    }
    sync();
  }
  document.addEventListener('selectionchange', () => { if (host) captureSelection(); });
  document.addEventListener('keydown', event => {
    if (!host || !event.altKey || event.ctrlKey || event.metaKey || event.repeat) return;
    if (event.composedPath().some(target => target.matches?.('input,textarea,select,[contenteditable="true"]'))) return;
    const name = {p:'pronounce', h:'hint', c:'check', a:'chat'}[event.key.toLowerCase()];
    if (name) { event.preventDefault(); event.stopPropagation(); action(name); }
  });
  window.SpanishHelper = {mount, receive, destroy};
})();
