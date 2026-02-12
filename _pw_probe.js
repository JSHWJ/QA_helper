const { chromium, firefox, webkit } = require('playwright');
async function test(name, launcher){
  try{
    const browser = await launcher.launch({headless:true, args:['--no-sandbox']});
    const page = await browser.newPage();
    await page.setContent('<html><body><div id="x" style="background: rgb(255, 212, 0)">N</div></body></html>');
    const out = await page.evaluate(()=>getComputedStyle(document.getElementById('x')).backgroundColor);
    console.log(name, 'OK', out);
    await browser.close();
  }catch(e){
    console.log(name, 'FAIL', String(e).slice(0,200));
  }
}
(async()=>{
  await test('chromium', chromium);
  await test('firefox', firefox);
  await test('webkit', webkit);
})();
