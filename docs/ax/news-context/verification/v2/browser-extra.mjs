import { chromium } from '../../../../../frontend/node_modules/playwright/index.mjs'
import assert from 'node:assert/strict'
import { writeFileSync } from 'node:fs'
const output = new URL('./', import.meta.url)
const results=[]
const browser=await chromium.launch({headless:true})
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const page=await context.newPage();page.setDefaultTimeout(6000)
const reset=()=>fetch('http://127.0.0.1:8027/__fixture/reset',{method:'POST'})
const observe=async()=>(await fetch('http://127.0.0.1:8027/__fixture/observations')).json()
const run=async(name,criteria,test)=>{try{await test();results.push({name,criteria,status:'PASS'})}catch(error){results.push({name,criteria,status:'FAIL',error:String(error)});await page.screenshot({path:new URL(`extra-failure-${results.length}.png`,output).pathname}).catch(()=>{})}}
const open=async()=>{await page.goto('http://127.0.0.1:5197/admin/news-analysis');await page.locator('#na-source').waitFor()}
const analyze=async(text='Arsenal의 Bukayo Saka가 축구 경기에서 뛰었다.')=>{await reset();await page.locator('#na-source').fill('https://source.example.invalid/post');await page.locator('#na-article').fill(text);await page.getByRole('button',{name:'글 분석하기',exact:true}).click();await page.getByText(/분석 완료 ·/).waitFor()}
const card=page.locator('#news-entity-card')
await open()
await run('overlapping, repeated, emoji and Latin boundaries from actual module',['AC-10'],async()=>{
 const actual=await page.evaluate(async()=>{
  const {articlePieces}=await import('/src/components/news-analysis/annotations.ts')
  const mention=(name,evidence)=>({mention:name,evidence,entity_type:'player',status:'linked',reason:'test',entity:{id:name.length,name,detail_path:'/players/test'}})
  const text='😀  José Silva의 축구.\nJosé Silva는 닉네임. Bukayo Saka가 축구한다.'
  const pieces=articlePieces(text,[mention('José Silva','José Silva의 축구.'),mention('Saka','Bukayo Saka가 축구한다.'),mention('Bukayo Saka','Bukayo Saka가 축구한다.')])
  return {original:text,joined:pieces.map(p=>p.text).join(''),highlighted:pieces.filter(p=>p.mention).map(p=>p.text),starts:pieces.filter(p=>p.mention).map(p=>p.start),bad:articlePieces('José SilvaExtra',[mention('José Silva','José SilvaExtra')]).filter(p=>p.mention).length}
 })
 assert.equal(actual.original,actual.joined);assert.deepEqual(actual.highlighted,['José Silva','Bukayo Saka']);assert.equal(actual.starts[0],4);assert.equal(actual.bad,0)
})
await run('detail error retry with actual GET on retry',['AC-12'],async()=>{
 await analyze();let calls=0
 await page.route('**/api/v1/players/bukayo-saka',async route=>{calls++;if(calls===1)await route.fulfill({status:503,json:{detail:'fixture detail unavailable'}});else await route.fulfill({response:await route.fetch()})})
 await page.locator('.annotated-name').filter({hasText:/^Bukayo Saka$/}).hover()
 await card.getByText('정보를 불러오지 못했습니다.').waitFor()
 await card.getByRole('button',{name:'정보 다시 불러오기'}).click()
 await card.getByText('2026 · Premier League').waitFor();assert.equal(calls,2)
 await page.screenshot({path:new URL('desktop-player-hover.png',output).pathname})
 await page.unroute('**/api/v1/players/bukayo-saka')
})
await run('slow team GET cannot replace current player; no polling',['AC-12'],async()=>{
 await analyze('Arsenal의 Bukayo Saka가 축구 경기에 출전했다.')
 await page.route('**/api/v1/teams/arsenal',async route=>{const response=await route.fetch();await new Promise(r=>setTimeout(r,700));await route.fulfill({response})})
 await page.locator('.annotated-name').filter({hasText:/^Arsenal$/}).hover();await card.getByText('정보를 불러오는 중입니다.').waitFor()
 await page.locator('.annotated-name').filter({hasText:/^Bukayo Saka$/}).hover();await card.getByText('2026 · Premier League').waitFor()
 await page.waitForTimeout(950);assert.match(await card.textContent(),/부카요 사카/);assert.doesNotMatch(await card.textContent(),/Fixture Stadium/)
 const before=JSON.stringify((await observe()).detail_gets);await page.waitForTimeout(1100);assert.equal(JSON.stringify((await observe()).detail_gets),before)
 await page.unroute('**/api/v1/teams/arsenal')
})
await run('double submit makes one API request',['AC-6'],async()=>{
 await reset();await page.locator('#na-article').fill('[SLOW] Arsenal football')
 const button=page.locator('button[type=submit]');await button.evaluate(el=>{el.click();el.click()})
 await page.getByText(/분석 완료 ·/).waitFor();assert.equal((await observe()).posts,1)
})
await run('390 admin entry is visible and clickable without header overlay',['AC-8'],async()=>{
 await page.setViewportSize({width:390,height:844})
 await page.route('**/api/v1/admin/management/**',route=>route.fulfill({json:{items:[],active:null,missing_count:0,scheduler_enabled:false}}))
 await page.goto('http://127.0.0.1:5197/admin')
 const link=page.getByRole('link',{name:'글 속 축구 정보',exact:true});await link.waitFor();await page.screenshot({path:new URL('admin-mobile.png',output).pathname})
 assert.equal(await link.evaluate(el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))}),true)
 await link.click();await page.locator('#na-source').waitFor();assert.match(page.url(),/admin\/news-analysis/)
 await page.unroute('**/api/v1/admin/management/**')
})
await run('role guard rejects USER and inactive; ADMIN allows',['AC-1'],async()=>{
 for(const [id,allowed] of [[3,false],[4,false],[2,true]]){
  const c=await browser.newContext();await c.addCookies([{name:'fixture_user',value:String(id),url:'http://127.0.0.1:5197'}]);const p=await c.newPage();await p.goto('http://127.0.0.1:5197/admin/news-analysis');await p.waitForTimeout(400);assert.equal(await p.locator('#na-source').count(),allowed?1:0);await c.close()
 }
})
writeFileSync(new URL('browser-extra-results.json',output),JSON.stringify({timestamp:new Date().toISOString(),scope:'actual app + localhost fixture API/SQLite. Detail error/delay injection only; admin list GETs stubbed empty for layout',results},null,2))
await browser.close();console.log(JSON.stringify(results,null,2));process.exitCode=results.some(r=>r.status==='FAIL')?1:0
