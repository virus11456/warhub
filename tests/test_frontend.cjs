process.chdir(require('path').resolve(__dirname,'..'));
const {JSDOM,VirtualConsole}=require('jsdom');const fs=require('fs');const assert=require('assert');
(async()=>{for(const mode of ['missing','legacy','new','valid']){
 const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented'))errors.push(e.message)});vc.on('warn',(...m)=>{if(String(m).includes('render error'))errors.push(m.join(' '))});
 const data=JSON.parse(fs.readFileSync('tests/fixtures/legacy-data.json'));
 if(['new','valid'].includes(mode)){data.updated_at=new Date().toISOString();data.score={model_version:'wpi-4.0',combined_score:mode==='valid'?42:null,coverage:.65,factors:{p:30,a:20,g:null,z:40,f:null,s:40,w:25},alert_level:'MODERATE'};data.regions=data.regions.map(r=>({...r,score:null,level:'INSUFFICIENT_DATA',coverage:0,factors:{}}));data.source_health={test:{label:'GDELT',status:'stale',note:'舊資料不計分'}};}
 if(mode==='valid'){data.score.factors.a=0;data.aviation={summary:{total:170}};data.firms={total_24h:11785};data.polymarket=[{question:'US strike on Cuba by December 31?',question_zh:'美國會在12月31日前打擊古巴嗎？',yes_price:.14,volume:1000,slug:'test'}];data.news=[{title:'English original',title_zh:'新聞繁體中文標題',url:'https://example.com/news',ts:data.updated_at}];data.strat={schema_version:2,ref_month:'2026-07',items:[{cmd:'4001',name:'天然橡膠',wan_ton:null,incomplete:true,reporters:0}]};data.strat_hist=[{ym:'2026-05',src:'mirror','4001':999},{ym:'2026-06',schema_version:2,src:'mirror','4001':2.2},{ym:'2026-07',schema_version:2,src:'mirror','4001':null}];}
 const dom=new JSDOM(fs.readFileSync('index.html','utf8'),{url:'https://warhub.test/',runScripts:'dangerously',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=async(url)=>{if(mode==='missing')return {ok:false,status:503};const u=new URL(url,'https://warhub.test/');if(u.pathname==='/api/data')return{ok:false,status:502}; if(u.pathname==='/data/data.json')return {ok:true,json:async()=>data};if(u.pathname.startsWith('/data/'))return{ok:true,json:async()=>(u.pathname.includes('history')?[]:{})};throw Error('disabled external request')};
  w.matchMedia=()=>({matches:true,addEventListener(){}}); w.IntersectionObserver=class{observe(){}disconnect(){}};w.ResizeObserver=class{observe(){}disconnect(){}};
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:()=>({width:20}),createRadialGradient:()=>({addColorStop(){}}),createLinearGradient:()=>({addColorStop(){}})},{get:(o,k)=>o[k]||(()=>{})});
 }});
 await new Promise(r=>setTimeout(r,1000));const d=dom.window.document;
 const result={mode,errors,wpi:d.querySelector('#hero-wpi-num')?.textContent,status:d.querySelector('#last-update-ts')?.textContent};console.log(JSON.stringify(result));assert.deepEqual(errors,[]);
 assert.ok(!d.body.textContent.includes('DEFCON 維持3級'));
 assert.ok(!d.body.textContent.includes('核武使用概率：5%'));
 assert.ok(!/準確率.{0,20}94%/.test(d.body.textContent));
 if(mode==='legacy'){
  assert.ok(!d.querySelector('#pizza-shops-grid').textContent.includes('CLOSED'));
  assert.ok(!d.querySelector('#food-grid').textContent.includes('9600.3%'));
  assert.ok(!d.querySelector('#ticker').textContent.includes('綜合威脅指數'));
 }
assert.equal(d.querySelector('#source-health'),null);
if(mode==='valid'){assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('170 架'));assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('異常分數 0'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('11,785 筆'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('暫不計分'));assert.ok(d.querySelector('#poly-list-container').textContent.includes('美國會在12月31日前打擊古巴嗎？'));assert.ok(d.querySelector('#news-list').textContent.includes('新聞繁體中文標題'));assert.ok(!d.querySelector('#news-list').textContent.includes('English original'));assert.ok(d.querySelector('#strat-grid').textContent.includes('最近歷史參考：2026-06'));assert.ok(d.querySelector('#sh-svg').textContent.includes('缺報'));assert.ok(!d.querySelector('#sh-svg').innerHTML.includes('999'));}
if(mode==='valid'){
  const w=dom.window;
  const trade={cmd:'4001',name:'天然橡膠',wan_ton:1,yoy_pct:-99,comparison_status:'current_incomplete',current_complete:false,reporter_codes:['764'],expected_reporter_codes:['764','360','458','704'],latest_complete:{month:'2026-03',wan_ton:0},incomplete:true};
  w.renderStrat({strat:{ref_month:'2026-07',items:[trade]}});
  assert.ok(d.querySelector('#strat-grid').textContent.includes('2026-03 · 0 萬噸'));
  assert.ok(!d.querySelector('#strat-grid').textContent.includes('99%'));
  assert.ok(d.querySelector('#strat-grid').textContent.includes('1/4 國'));
  w.renderFood({food:{ref_month:'2026-07',items:[{...trade,cmd:'1201',name:'大豆'}]}});
  assert.ok(d.querySelector('#food-grid').textContent.includes('最新完整月份'));
  assert.ok(!d.querySelector('#food-grid').textContent.includes('99%'));

  const official=(date,aircraft)=>({date,aircraft,ships:0,verified:true,source_kind:'mnd_daily_report',source_url:'https://air.mnd.gov.tw/TW/News/News_Detail.aspx?CID=213&ID=59225'});
  w.renderPla({pla:{days:[official('2026-09-01',0),{date:'2026-09-02',aircraft:999},official('2026-09-03',6)],baseline:3}});
  const tips=[...d.querySelectorAll('#pla-svg [data-tip]')].map(x=>x.getAttribute('data-tip'));
  assert.equal(tips.length,2); assert.ok(tips[0].includes('共機 0 架次')); assert.ok(!tips.join('').includes('999'));
  assert.ok(d.querySelector('#pla-note').textContent.includes('06:00'));
  assert.ok(d.querySelector('#pla-legend a').href.includes('air.mnd.gov.tw'));
  w.renderPla({pla:{days:[]}}); assert.equal(d.querySelector('#pla-svg').innerHTML,'');
  assert.equal(d.querySelector('#pla-legend a'),null);

  assert.equal(w.zhMarket('Will Russia test a nuclear weapon by December 31?'), '中文翻譯暫時無法取得（點擊查看原文）');
  assert.equal(w.zhMarket('中文市場問題？'), '中文市場問題？');
  assert.equal(w.chineseTitle('English mistranslation', 'English original'), '中文翻譯暫時無法取得（點擊查看原文）');
  assert.equal(w.chineseTitle(null, '中文原標題'), '中文原標題');
  w.renderPolymarketCards([{question:'Unknown future question?',yes_price:.2,volume:500,slug:'untranslated-test'}]);
  const card=d.querySelector('#poly-list-container');
  assert.ok(card.textContent.includes('中文翻譯暫時無法取得'));
  assert.ok(!card.textContent.includes('Unknown future question'));
  assert.equal(card.querySelector('.poly-question').title,'Unknown future question?');
  assert.equal(card.querySelector('a').href,'https://polymarket.com/market/untranslated-test');
  assert.ok(card.textContent.includes('20%'));
}
assert.equal(result.wpi,mode==='valid'?'42':'--');dom.window.close();
}})().catch(e=>{console.error(e);process.exit(1)});
