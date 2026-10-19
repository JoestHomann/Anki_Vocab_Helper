async page => {
  const heading = page.getByRole('heading', { name: 'ahorrar', exact: true });
  await page.evaluate(() => {
    window.__savedPycmd = window.pycmd;
    window.__selectionRequests = [];
    window.pycmd = message => {
      const request = JSON.parse(message.slice('spanish-helper:'.length));
      window.__selectionRequests.push(request);
      window.SpanishHelper.receive({event: 'audio', token: request.token, word: request.selection || 'ahorrar'});
    };
  });
  try {
    await heading.evaluate(element => {
      const range = document.createRange();
      range.setStart(element.firstChild, 0);
      range.setEnd(element.firstChild, 6);
      const selection = window.getSelection();
      selection.removeAllRanges(); selection.addRange(range);
    });
    await page.getByRole('button', { name: 'Pronunciar Alt P', exact: true }).click();
    await page.evaluate(() => window.getSelection().removeAllRanges());
    await page.getByRole('button', { name: 'Pronunciar Alt P', exact: true }).click();
    const requests = await page.evaluate(() => window.__selectionRequests);
    if (requests[0].selection !== 'ahorra') throw new Error('Selected text was not sent');
    if (requests[1].selection !== '') throw new Error('Cleared selection is still being used');
    return 'PASS: selected text is used; clearing selection restores the whole card word';
  } finally {
    await page.evaluate(() => { window.pycmd = window.__savedPycmd; delete window.__savedPycmd; });
  }
}
