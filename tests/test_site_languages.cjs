/* Full guide text coverage and dashboard refresh in both languages, offline. */
const fs=require('node:fs'),assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const catalog={...JSON.parse(fs.readFileSync('locales/en.json','utf8')),
 ...(fs.existsSync('locales/overrides.json')?JSON.parse(fs.readFileSync('locales/overrides.json','utf8')):{})};
const runtime=fs.readFileSync('i18n.js','utf8');
const wait=()=>new Promise(r=>setImmediate(r));
function visibleStrings(d){
 const strings=[],walker=d.createTreeWalker(d.body,4);let node;
 while(node=walker.nextNode())if(!node.parentElement?.closest('script,style,[data-language-control]'))strings.push(node.nodeValue);
 return strings;
}
(async()=>{
 for(const file of fs.readdirSync('guides').filter(f=>f.endsWith('.html'))){
  const dom=new JSDOM(fs.readFileSync('guides/'+file,'utf8'),{url:'https://warhub.test/guides/'+file,runScripts:'outside-only'});
  const w=dom.window,d=w.document,original=visibleStrings(d),links=[...d.links].map(a=>a.href);
  w.WARHUB_EN=catalog;w.eval(runtime);d.dispatchEvent(new w.Event('DOMContentLoaded'));
  assert.equal(d.documentElement.lang,'zh-TW');w.WarhubI18n.select('en');await wait();
  const missing=visibleStrings(d).filter(s=>/[\u3400-\u9fff]/.test(s));
  assert.deepEqual(missing,[],file+' untranslated visible text');
  assert.deepEqual([...d.links].map(a=>a.href),links);
  w.WarhubI18n.select('zh-TW');await wait();assert.deepEqual(visibleStrings(d),original,file+' original restoration');w.close();
 }
 const errors=[],vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented'))errors.push(e.message)});
 const data=JSON.parse(fs.readFileSync('tests/fixtures/legacy-data.json','utf8'));
 data.updated_at=new Date().toISOString();data.score={model_version:'wpi-4.0',combined_score:null,coverage:0,factors:{}};
 data.polymarket=[{question:'Will the event happen by December 31?',question_zh:'事件會在12月31日前發生嗎？',yes_price:.14,volume:1000,slug:'test'}];
 data.news=[{title:'中文測試標題',title_zh:'中文測試標題',title_en:'Original test headline',url:'https://example.com/news',ts:data.updated_at}];
 data.taiwan_insight={version:1,as_of:data.updated_at,activity:{status:'within_baseline',baseline_days:20,median:10,latest:{date:data.updated_at.slice(0,10),aircraft:0,ships:5,government_ships:0,period_end:data.updated_at,source_url:'https://example.com/report'}},
  news:{input_status:'partial',sample_24h:2,publishers_24h:1,latest_at:data.updated_at},
  markets:[{slug:'test',question:'Will the event happen by December 31?',question_zh:'事件會在12月31日前發生嗎？',yes_percent:14,delta_pp:0,comparison_at:new Date(Date.now()-24*3600000).toISOString(),end_date:'2030-01-01T00:00:00Z'}],timeline:[]};
 data.notams={taiwan:{provider:'NOTAC',stale:true,latest_attempt:{complete:false,partial:true,sample_count:40,reported_count:600,sample_danger:0,sample_closure:0,sample_order:'newest',sample_timing:{current:20,future:10,ended:0,unknown:10},fetched_at:data.updated_at}}};
 let calls=0;
 const dom=new JSDOM(fs.readFileSync('index.html','utf8'),{url:'https://warhub.test/',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.WARHUB_EN=catalog;
  w.fetch=async(url)=>{calls++;const u=new URL(url,'https://warhub.test/');if(u.pathname==='/api/data')return{ok:false,status:502};if(u.pathname==='/data/data.json')return{ok:true,json:async()=>JSON.parse(JSON.stringify(data))};return{ok:true,json:async()=>u.pathname.includes('history')?[]:{}};};
  w.matchMedia=()=>({matches:true,addEventListener(){}});w.IntersectionObserver=class{observe(){}disconnect(){}};w.ResizeObserver=class{observe(){}disconnect(){}};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:()=>({width:20}),createRadialGradient:()=>({addColorStop(){}}),createLinearGradient:()=>({addColorStop(){}})},{get:(o,k)=>o[k]||(()=>{})});
 }});
 const w=dom.window,d=w.document;w.eval(fs.readFileSync('cross-context.js','utf8'));w.eval(runtime);
 await new Promise(r=>setTimeout(r,1000));
 const before=calls;w.WarhubI18n.select('en');await wait();
 assert.equal(calls,before,'switch did not fetch');assert.equal(d.documentElement.lang,'en');assert.deepEqual(errors,[]);
 assert.ok(d.querySelector('#news-list').textContent.includes('Original test headline'));
 assert.ok(d.querySelector('#poly-list-container').textContent.includes('Will the event happen by December 31?'));
 assert.ok(d.querySelector('#poly-list-container').textContent.includes('14%'));
 assert.ok(d.querySelector('#cross-reading').textContent.includes('40'));
 assert.ok(d.querySelector('#cross-reading').textContent.includes('600'));
 assert.ok(d.querySelector('#notac-body').textContent.includes('records'));
 assert.ok(!/\bPen\b/.test(d.querySelector('#cross-reading').textContent));
 assert.ok(d.querySelector('#cross-reading').textContent.includes('0'));
 const missing=visibleStrings(d).filter(s=>/[\u3400-\u9fff]/.test(s));
 assert.deepEqual(missing,[],'dashboard untranslated UI text');
 data.news[0].title='更新中文標題';data.news[0].title_zh='更新中文標題';data.news[0].title_en='Updated English headline';
 w.WarhubI18n.registerData(data);w.renderNews(data);await wait();assert.ok(d.querySelector('#news-list').textContent.includes('Updated English headline'));
 w.WarhubI18n.select('zh-TW');await wait();assert.ok(d.querySelector('#news-list').textContent.includes('更新中文標題'));
 w.close();console.log('21 guide pages and dashboard: Chinese defaults, English coverage, dynamic refresh, links and values verified');
})().catch(e=>{console.error(e);process.exit(1)});
