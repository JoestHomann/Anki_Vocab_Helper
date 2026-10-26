/* Browser regression checks. Requires Playwright; no network calls or API key. */
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const css = fs.readFileSync(path.join(root, 'spanish_helper/web/overlay.css'), 'utf8');
const js = fs.readFileSync(path.join(root, 'spanish_helper/web/overlay.js'), 'utf8');
const ankiStyle = process.env.ANKI_WEBVIEW_CSS;
const nativeCSS = ankiStyle ? fs.readFileSync(ankiStyle, 'utf8') : '';

(async () => {
  const browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_PATH ? {executablePath: process.env.CHROMIUM_PATH} : {})});
  try {
    const page = await browser.newPage({viewport:{width:1100, height:680}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.setContent('<!doctype html><html><head><style>' + nativeCSS + '</style><style>body{margin:0;font-family:Arial,sans-serif}#qa{padding:70px 30px;text-align:center;font-size:26px}#qa hr{margin:25px auto;max-width:600px;border:0;border-top:1px solid var(--border,#ccc)}</style></head><body class="fancy isWin"><div id="qa"><h1 style="font:inherit">embarazada</h1><hr><div>verlegen</div></div></body></html>');
    await page.addScriptTag({content:js});
    await page.evaluate(() => {window.requests = []; window.pycmd = value => window.requests.push(JSON.parse(value.slice('spanish-helper:'.length)));});
    const mount = async (token, answerShown=true) => page.evaluate(({css,token,answerShown}) => window.SpanishHelper.mount({token,word:'embarazada',answerShown},css), {css,token,answerShown});
    const receive = async result => page.evaluate(value => window.SpanishHelper.receive(value), result);
    const checkButton = page.getByRole('button', {name:'Comprobar traducción',exact:true});
    await mount('question', false);
    assert.equal(await checkButton.isDisabled(), true);
    await page.keyboard.press('Alt+c');
    assert.equal(await page.evaluate(() => window.requests.length), 0);
    assert.equal(await page.locator('#spanish-helper').evaluate(host => host.getBoundingClientRect().height < 60), true);
    await mount('answer');
    await page.locator('#qa h1').evaluate(element => {
      const range=document.createRange();range.selectNodeContents(element);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    });
    await checkButton.click();
    assert.equal(await checkButton.isDisabled(), true);
    const requests = await page.evaluate(() => window.requests);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].action, 'check');
    assert.equal(requests[0].selection, '');
    assert.equal(requests[0].selectionOnCard, false);
    await receive({event:'check',token:'old',verdict:'correct',explanation:'stale result'});
    assert.equal(await page.locator('#check-panel').isVisible(), false);
    await receive({event:'check',token:'answer',verdict:'incorrect',saved:'verlegen',explanation:'«Embarazada» significa que una mujer espera un bebé, no que siente vergüenza.',suggestion:'schwanger',source:'Prueba de interfaz · respuesta simulada'});
    assert.equal(await page.getByText('Posible error',{exact:true}).isVisible(), true);
    assert.equal(await page.getByText('schwanger',{exact:true}).isVisible(), true);
    await page.getByRole('button',{name:'Cerrar comprobación',exact:true}).click();
    assert.equal(await page.locator('#check-panel').isVisible(), false);
    await page.keyboard.press('Alt+c');
    assert.equal(await page.locator('#check-panel').isVisible(), true);
    assert.equal(await page.evaluate(() => window.requests.length), 1);
    await page.evaluate(() => {document.body.classList.add('nightMode');document.documentElement.classList.add('night-mode');});
    await page.waitForFunction(() => document.getElementById('spanish-helper').dataset.dark === 'true');
    if (nativeCSS) {
      assert.equal(await page.locator('.helper').evaluate(element => getComputedStyle(element).backgroundColor), 'rgb(44, 44, 44)');
      assert.equal(await checkButton.evaluate(element => getComputedStyle(element).borderRadius), '15px');
    }
    const output = path.join(root, 'output/screenshots'); fs.mkdirSync(output,{recursive:true});
    await page.screenshot({path:path.join(output,'anki-dark-check.png')});
    await page.evaluate(() => {document.body.classList.remove('nightMode');document.documentElement.classList.remove('night-mode');});
    await page.waitForFunction(() => document.getElementById('spanish-helper').dataset.dark === 'false');
    await page.screenshot({path:path.join(output,'anki-light-check.png')});
    await page.getByRole('button',{name:'Cerrar comprobación',exact:true}).click();
    await page.screenshot({path:path.join(output,'anki-light-toolbar.png')});
    for (const width of [320,375,410,768]) {
      await page.setViewportSize({width,height:480});
      const buttons = await page.locator('.actions button').evaluateAll(elements => elements.map(element => {const rect=element.getBoundingClientRect();return {left:rect.left,right:rect.right};}));
      assert.equal(buttons.every(rect => rect.left >= 0 && rect.right <= width), true, 'Toolbar overflow at ' + width);
    }
    await page.setViewportSize({width:375,height:480});
    await checkButton.click();
    await page.screenshot({path:path.join(output,'anki-narrow-check.png')});
    await mount('next');
    assert.equal(await page.locator('#check-panel').isVisible(), false);
    await checkButton.click();
    await receive({event:'error',token:'next',action:'check',message:'Añade tu clave de OpenAI en Herramientas → Spanish Helper.'});
    assert.equal(await checkButton.isEnabled(),true);
    assert.equal(await page.getByText('Añade tu clave de OpenAI en Herramientas → Spanish Helper.').isVisible(),true);
    // Existing selection behavior must continue working for audio.
    await page.evaluate(() => window.getSelection().removeAllRanges());
    await page.getByRole('button',{name:'Pronunciar',exact:true}).click();
    assert.equal(await page.evaluate(() => window.requests.at(-1).selection), '');
    await receive({event:'audio',token:'next',action:'pronounce'});
    await page.getByRole('button',{name:'Pista',exact:true}).click();
    await receive({event:'hint',token:'next',example:'Cada semana intento ahorrar un poco para mis próximas vacaciones.',explanation:'Guardar dinero para usarlo después.',source:'Prueba local'});
    const exampleButton = page.getByRole('button',{name:'Escuchar ejemplo',exact:true});
    assert.equal(await exampleButton.isVisible(), true);
    // Text selections in the card must not override the example sentence.
    await page.locator('#qa h1').evaluate(element => {
      const range=document.createRange();range.selectNodeContents(element);
      const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
    });
    await exampleButton.click();
    assert.equal(await exampleButton.isDisabled(),true);
    assert.equal(await page.getByRole('button',{name:'Pronunciar',exact:true}).isDisabled(),true);
    assert.equal(await page.evaluate(() => window.requests.at(-1).action),'example_audio');
    assert.equal(await page.evaluate(() => window.requests.at(-1).selection),'');
    await receive({event:'error',token:'next',action:'example_audio',message:'No hay conexión con el servicio.'});
    assert.equal(await exampleButton.isEnabled(),true);
    await exampleButton.click();
    await receive({event:'audio',token:'old',action:'example_audio'});
    assert.equal(await exampleButton.isDisabled(),true);
    await receive({event:'audio',token:'next',action:'example_audio'});
    assert.equal(await exampleButton.isEnabled(),true);
    await page.evaluate(() => window.getSelection().removeAllRanges());
    await page.screenshot({path:path.join(output,'anki-hint-example-audio.png')});
    await receive({event:'hint',token:'next',example:'',explanation:'Una definición sin ejemplo.',source:'Prueba local'});
    assert.equal(await exampleButton.isVisible(), false);
    await mount('new-card');
    assert.equal(await exampleButton.isVisible(), false);
    await page.evaluate(css => window.SpanishHelper.mount({token:'plan-card',word:'hola',answerShown:true,usingChatGPT:true},css),css);
    assert.equal(await page.getByText('Using ChatGPT plan ·').isVisible(),true);
    assert.equal(await page.getByRole('link',{name:'Manage usage',exact:true}).getAttribute('href'),'https://chatgpt.com/settings/usage');
    assert.deepEqual(errors, []);
    console.log('PASS: native themes, responsive toolbar, translation checks and example speaker: visibility, selected-text isolation, busy state, errors, stale replies and card reset');
  } finally { await browser.close(); }
})().catch(error => {console.error(error);process.exitCode=1;});
