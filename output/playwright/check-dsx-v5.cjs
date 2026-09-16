// Isolated, repeatable regression check; no production network calls.
const fs=require('node:fs'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/이주원/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{
 const file='C:/Users/이주원/Documents/ChatGPT/DSX/output/dsx-agent-studio-site/dist/index.html';
 const server=http.createServer((q,s)=>{s.setHeader('Content-Type','text/html; charset=utf-8');s.end(fs.readFileSync(file));});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const p=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],external=[];p.setDefaultTimeout(5000);
 p.on('pageerror',e=>errors.push(e.message));await p.route('**/*',r=>{if(new URL(r.request().url()).origin!==origin){external.push(r.request().url());return r.abort();}return r.continue();});
 const content=p.locator('#dsx-page'),nav=v=>p.locator('.menu [data-go="'+v+'"]').click(),step=()=>content.locator('[data-job-step]').click();
 await p.goto(origin);assert((await p.locator('#dsx-crumb').innerText()).includes('S01'));
 await p.locator('[data-action="toggle-assistant"]').click();const panel=p.locator('#dsx-assistant');
 const ask=async q=>{await panel.locator('textarea').fill(q);await panel.locator('button[type=submit]').click();};
 await ask('GPU 메모리 점유와 활동률은 어떻게 달라?');assert((await panel.innerText()).includes('일반 답변'));await ask('<img src=x onerror=alert(1)>');assert.equal(await panel.locator('.chat-question img').count(),0);
 await panel.locator('[data-action="close-chat"]').click();await nav('fleet');await content.locator('[data-fleet-tab="workloads"]').click();assert((await content.innerText()).includes('matched'));await content.locator('[data-mapping-time]').selectOption('past');assert((await content.innerText()).includes('과거 관계 부족'));
 await nav('cases');await content.locator('[data-go="home"]').click();await content.locator('[name="symptom"]').fill('응답 중단 조사');await content.locator('[type=submit]').click();assert((await content.innerText()).includes('접수 대기'));
 await step();await content.locator('[data-job-cancel]').click();assert((await content.innerText()).includes('최종 취소 상태'));assert.equal(await content.locator('[data-job-result]').count(),0);
 // Completion may win a cancellation race; terminal controls must disappear.
 await step();await step();await step();assert.equal(await content.locator('[data-job-cancelled]').count(),0);assert((await content.innerText()).includes('부분 산출'));
 await content.locator('[data-job-result]').click();assert((await content.innerText()).includes('사건 연결 없음'));
 await content.locator('[data-job-reanalyze]').click();assert((await content.innerText()).includes('이전 작업 JOB-102'));await step();await content.locator('[data-job-fail]').click();await content.locator('[data-job-retry]').click();await step();assert((await content.innerText()).includes('시도 2'));
 await content.locator('[data-job-cancel]').click();await content.locator('[data-job-cancelled]').click();assert((await content.innerText()).includes('취소 완료'));
 await nav('reports');await content.locator('[data-save-analysis]').click();await content.locator('[name="start"]').fill('2026-09-08');await content.locator('[name="end"]').fill('2026-09-14');await content.locator('[name="topics"][value="allocation"]').check();await content.locator('[type=submit]').click();assert((await content.innerText()).includes('접수 대기'));for(let i=0;i<4;i++)await step();await content.locator('[data-job-result]').click();assert((await content.innerText()).includes('2026-09-08'));assert((await content.innerText()).includes('과거 할당'));
 await content.locator('[name="review"]').fill('첫 보고서 검토');await content.locator('[type=submit]').click();
 await nav('reports');await content.locator('[data-save-analysis]').click();await content.locator('[name="start"]').fill('2026-09-15');await content.locator('[name="end"]').fill('2026-09-16');await content.locator('[type=submit]').click();
 await nav('reports');await content.locator('[data-open-report-job="JOB-104"]').click();assert((await content.innerText()).includes('2026-09-08'));assert.equal(await content.locator('[name="review"]').inputValue(),'첫 보고서 검토');
 await nav('settings');await content.locator('[data-model-add]').click();const form=content.locator('[data-form="model-save"]');await form.locator('[name="name"]').fill('검증 모델');await form.locator('[name="model"]').fill('local-demo');await form.locator('[name="ip"]').fill('999.0.0.1');await form.locator('[type=submit]').click();assert((await content.locator('#model-error').innerText()).includes('0~255'));await form.locator('[name="ip"]').fill('10.20.0.15');await form.locator('[type=submit]').click();
 await content.locator('.settings-tabs [data-settings-tab="routing"]').click();await content.locator('[name="default"]').selectOption({label:'검증 모델'});await content.locator('[type=submit]').click();await p.reload();assert.equal(await content.locator('[name="default"] option:checked').innerText(),'검증 모델');
 for(const width of [1440,1100,736,390,320]){await p.setViewportSize({width,height:900});for(const v of ['dashboard','fleet','jobs','reports','settings']){await nav(v);assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow ${width} ${v}`);}}
 await p.locator('[data-action="toggle-assistant"]').click();assert(await panel.isVisible());const box=await panel.locator('[type=submit]').boundingBox();assert(box&&box.y+box.height<=901,'composer clipped');
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);console.log('PASS: chat scope/XSS, mapping axes, job acceptance/cancel race/retry/reanalysis, immutable report snapshots/reviews, endpoint validation/persistence, 5 viewport sizes, no external calls.');
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
