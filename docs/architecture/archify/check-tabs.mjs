import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { createServer } from 'node:http';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
const dir = path.dirname(fileURLToPath(import.meta.url));
const skill = process.env.ARCHIFY_SKILL_DIR || path.join(os.homedir(), '.agents/skills/archify');
const { ChromeVisualBrowser } = await import(pathToFileURL(path.join(skill, 'bin/visual-check.mjs')));
const chrome = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = new ChromeVisualBrowser(chrome);
const types = ['architecture','sequence','sequence-rca-execution','sequence-report-request','sequence-report-schedule','sequence-report-execution'];
const files = ['gpu-ops-advisor.html', ...types.map(type => 'gpu-ops-advisor.'+type+'.html')];
const server = createServer((req,res) => {
  const name = req.url.split('?')[0].slice(1);
  if (!files.includes(name)) {
    res.writeHead(404).end(); return;
  }
  res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
  res.end(fs.readFileSync(path.join(dir,name)));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const url = 'http://127.0.0.1:'+server.address().port+'/gpu-ops-advisor.html';
const rows = [];
const session = await browser.sessionPromise;
async function evaluate(expression) {
  const result = await browser.cdp.send('Runtime.evaluate', { expression, awaitPromise:true, returnByValue:true }, session);
  assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
try {
  for (const [width,height] of [[1440,900],[1600,1000],[1920,1080],[2048,1320]]) {
    await browser.cdp.send('Emulation.setDeviceMetricsOverride', {width,height,deviceScaleFactor:1,mobile:false}, session);
    const loaded=browser.cdp.waitFor('Page.loadEventFired',session);
    await browser.cdp.send('Page.navigate',{url},session);
    await loaded;
    for (const type of [...types,'architecture']) {
      if (type === 'architecture' || type === 'sequence') {
        await evaluate(`document.querySelector('a[href="#${type}"]').click()`);
      } else {
        await evaluate(`document.getElementById('scenario').value='${type}';document.getElementById('scenario').dispatchEvent(new Event('change'))`);
      }
      // Let the frame navigation and its responsive layout settle before measuring.
      const metrics=await evaluate(`(async()=>{
        const f=document.getElementById('diagram');
        for(let i=0;i<100;i++){
          try{if(f.contentDocument?.readyState==='complete' && f.contentWindow.location.pathname.endsWith('.${type}.html') && f.contentDocument.querySelector('svg'))break;}catch{}
          await new Promise(r=>setTimeout(r,50));
        }
        const w=f.contentWindow,d=f.contentDocument;
        await d.fonts.ready;
        await w.Archify?.readerLayout?.whenStable?.();
        await w.Archify?.viewerChromeLayout?.whenStable?.();
        await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        return {type:'${type}',selected:document.querySelector('nav [aria-current]')?.hash,
          title:f.title,url:w.location.pathname,svg:!!d.querySelector('svg'),
          outer:[innerWidth,innerHeight,document.documentElement.scrollWidth,document.documentElement.scrollHeight],
          inner:[w.innerWidth,w.innerHeight,d.documentElement.scrollWidth,d.documentElement.scrollHeight]};
      })()`);
      assert.equal(metrics.selected,type === 'architecture' ? '#architecture' : '#sequence');
      if(type !== 'architecture') assert.equal(await evaluate("document.getElementById('scenario').value"),type);
      assert.ok(metrics.url.endsWith('.'+type+'.html'));
      assert.ok(metrics.svg);
      for(const [w,h,sw,sh] of [metrics.outer,metrics.inner]) {
        assert.ok(sw<=w && sh<=h,JSON.stringify(metrics));
      }
      rows.push({width,height,...metrics});
      if(width===1440){
        const capture=await browser.cdp.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false},session);
        fs.writeFileSync(path.join(dir,'tabs.'+type+'.png'),Buffer.from(capture.data,'base64'));
      }
    }
  }
  // Direct links and invalid hashes must resolve predictably.
  for(const [hash,expected] of [...types.map(type=>['#'+type,type]),['#unknown','architecture']]){
    await evaluate(`location.hash=${JSON.stringify(hash)}`);
    await evaluate('new Promise(r=>setTimeout(r,100))');
    assert.equal(await evaluate("document.querySelector('nav [aria-current]').hash"),expected==='architecture' ? '#architecture' : '#sequence');
    assert.equal(await evaluate("document.getElementById('diagram').getAttribute('src')"),'gpu-ops-advisor.'+expected+'.html');
  }
  // Smoke-check direct file opening too; each file frame has its own origin.
  const fileLoaded=browser.cdp.waitFor('Page.loadEventFired',session);
  await browser.cdp.send('Page.navigate',{url:pathToFileURL(path.join(dir,'gpu-ops-advisor.html')).href+'#sequence'},session);
  await fileLoaded;
  const tree=await browser.cdp.send('Page.getFrameTree',{},session);
  const child=tree.frameTree.childFrames.find(f=>f.frame.url.endsWith('.sequence.html'));
  assert.ok(child,'File opening must load the Sequence frame');
  const world=await browser.cdp.send('Page.createIsolatedWorld',{frameId:child.frame.id,worldName:'tabs-file-check'},session);
  const fileSvg=await browser.cdp.send('Runtime.evaluate',{expression:"!!document.querySelector('svg')",contextId:world.executionContextId,returnByValue:true},session);
  assert.equal(fileSvg.result.value,true);
  const binding = {};
  for(const name of files){
    const bytes=fs.readFileSync(path.join(dir,name));
    binding[name]={sha256:createHash('sha256').update(bytes).digest('hex'),bytes:bytes.length};
  }
  fs.writeFileSync(path.join(dir,'tabs-check.json'),JSON.stringify({status:'pass',binding,checks:rows},null,2));
  console.log('PASS: both tabs and all 5 sequence scenarios, 4 viewports, frame/outer containment, direct links and invalid-hash fallback.');
} finally { await browser.close(); await new Promise(resolve=>server.close(resolve)); }
