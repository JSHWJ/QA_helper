const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1700, height: 1000 } });
  await page.goto('http://127.0.0.1:8050', { waitUntil: 'networkidle', timeout: 120000 });
  await page.waitForSelector('.ag-root-wrapper', { timeout: 120000 });
  await page.waitForTimeout(2500);
  const result = await page.evaluate(() => {
    const colIds = ['KO_Match', 'EN_Match', 'RU_Match', 'Overall_Match'];
    const rows = document.querySelectorAll('.ag-center-cols-container .ag-row');
    let found = null;
    for (const row of rows) {
      for (const col of colIds) {
        const cell = row.querySelector(`.ag-cell[col-id="${col}"]`);
        if (!cell) continue;
        const txt = (cell.textContent || '').trim().toUpperCase();
        if (txt === 'N') {
          const cs = getComputedStyle(cell);
          found = {
            col,
            text: txt,
            backgroundColor: cs.backgroundColor,
            color: cs.color,
            fontWeight: cs.fontWeight,
            className: cell.className,
          };
          break;
        }
      }
      if (found) break;
    }
    return {
      found,
      rowCount: rows.length,
      noDataText: document.body.innerText.includes('표시할 데이터가 없습니다')
    };
  });
  console.log(JSON.stringify(result, null, 2));
  await page.screenshot({ path: 'dash_check.png', fullPage: true });
  await browser.close();
})();
