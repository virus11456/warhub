require('./test_kalshi_frontend.cjs');
process.chdir(require('path').resolve(__dirname,'..'));
const {JSDOM,VirtualConsole}=require('jsdom');const fs=require('fs');const assert=require('assert');
{
 const cash=fs.readFileSync('guides/cash-finance.html','utf8');
 const stocktoolsDeep=['https://www.stocktools.cc/tw/us-fee-calculator','https://www.stocktools.cc/tw/us-etf','https://www.stocktools.cc/tw/us-deposit','https://www.stocktools.cc/tw/us-open-account','https://www.stocktools.cc/tw/us-dividend','https://www.stocktools.cc/tw/us-first-buy','https://www.stocktools.cc/tw/us-premarket','https://www.stocktools.cc/tw/us-order-types','https://www.stocktools.cc/tw/us-adr','https://www.stocktools.cc/tw/us-fx','https://www.stocktools.cc/tw/us-fractional','https://www.stocktools.cc/tw/us-earnings'];
 for(const href of stocktoolsDeep) assert.ok(cash.includes(`href="${href}"`), href+' missing from cash-finance');
 assert.ok(cash.includes('href="https://stocktools.cc/"') && cash.includes('href="https://toolist.cc/"'));
 assert.ok(!/firstrade|luxstay|moneytools/i.test(cash));
}
(async()=>{for(const mode of ['missing','legacy','new','valid']){
 const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented'))errors.push(e.message)});vc.on('warn',(...m)=>{if(String(m).includes('render error'))errors.push(m.join(' '))});
 const data=JSON.parse(fs.readFileSync('tests/fixtures/legacy-data.json'));
 if(['new','valid'].includes(mode)){data.updated_at=new Date().toISOString();data.score={model_version:'wpi-4.0',combined_score:mode==='valid'?42:null,coverage:.65,factors:{p:30,a:20,g:null,z:40,f:null,s:40,w:25},alert_level:'MODERATE'};data.regions=data.regions.map(r=>({...r,score:null,level:'INSUFFICIENT_DATA',coverage:0,factors:{}}));data.source_health={test:{label:'GDELT',status:'stale',note:'舊資料不計分'}};}
 if(mode==='valid'){data.usda={...(data.usda||{}),schema_version:2,week_ending:'2026-10-15',items:[{name:'大豆',market_year:2027,week:'2026-10-15',week_net_kt:0,next_year_net_kt:null,outstanding_kt:9126},{name:'小麥',market_year:2027,week:null,week_net_kt:null,next_year_net_kt:null,outstanding_kt:null,stale:true},{name:'玉米',market_year:2027}]};data.score.factors.a=0;data.aviation={summary:{total:170}};data.firms={total_24h:11785};data.polymarket=[{question:'US strike on Cuba by December 31?',question_zh:'美國會在12月31日前打擊古巴嗎？',yes_price:.14,volume:1000,slug:'test'}];data.news=[{title:'English original',title_zh:'新聞繁體中文標題',url:'https://example.com/news',ts:data.updated_at}];data.strat={schema_version:2,ref_month:'2026-07',items:[{cmd:'4001',name:'天然橡膠',wan_ton:null,incomplete:true,reporters:0}]};data.strat_hist=[{ym:'2026-05',src:'mirror','4001':999},{ym:'2026-06',schema_version:2,src:'mirror','4001':2.2},{ym:'2026-07',schema_version:2,src:'mirror','4001':null}];}
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
  assert.ok(!d.querySelector('#food-grid').textContent.includes('9600.3%'));
  assert.ok(!d.querySelector('#ticker').textContent.includes('綜合威脅指數'));
 }
assert.equal(d.querySelector('#source-health'),null);
const experimental=d.querySelector('#experimental-observations');
assert.ok(experimental && !experimental.open); // experimental WPI block collapsed by default
assert.equal(experimental.parentElement.className,'container');
// Pizza & bars are the lead feature: first on the page, outside the collapsed WPI block.
const pizzaCard=d.querySelector('#pizza-card');
assert.equal(pizzaCard.parentElement.firstElementChild,pizzaCard);
assert.ok(!experimental.contains(pizzaCard));
for(const selector of ['.hero-strip','.wpi-section']) {
  assert.equal(d.querySelectorAll(selector).length,1);
  assert.ok(experimental.contains(d.querySelector(selector)));
}
// Radar summary: setup, off-hours, no-live and hot states are told apart; nothing implies closed shops or safety.
{const R=j=>{d.defaultView.renderPizzaRadar(j);return d.querySelector('#pizza-radar-summary');};
const two=[{name:'a',busyness:null},{name:'b',busyness:null}];
assert.ok(R({pizza:two,pizza_summary:{state:'setup_needed'}}).textContent.includes('尚未在 BestTime 建檔'));
assert.ok(R({pizza:two,pizza_summary:{state:'off_hours'}}).textContent.includes('只在美東 16–24 時查詢'));
const none=R({pizza:two,pizza_summary:{state:'no_live',queried_at:'2026-10-29T00:10:00Z'}}).textContent;
assert.ok(none.includes('2 家店都沒有即時人流')&&none.includes('20:10')&&none.includes('不等於店家打烊'));
assert.ok(!/PizzINT|pizzint/i.test(d.querySelector('#pizza-card').textContent));
const hot=R({pizza:[{name:'a',busyness:80,percentage_of_usual:180,status:'spike'},{name:'b',busyness:30,percentage_of_usual:90,status:'normal'}],pizza_summary:{state:'ok'}});
assert.ok(hot.textContent.includes('1 家店人流高於平常（最高為平常的 180%）'));assert.ok(hot.classList.contains('hot'));}
// Level, index and bars: a missing index is not shown as 0.
{const w=d.defaultView;w.renderPizzaBlock({pizza:[],pizza_summary:{level:'busy',index:0},bars:{available:true,emptiness:30,avg_delta:-30,open_count:3,total:4}});
assert.equal(d.querySelector('#pizza-level').textContent,'偏忙');assert.ok(d.querySelector('#pizza-index').textContent.includes('異常指數 0 / 100'));
assert.ok(d.querySelector('#pizza-bars-line').textContent.startsWith('異常冷清（比平常 -30%，3/4'));
w.renderPizzaBlock({pizza:[],pizza_summary:{level:null,index:null},bars:{available:false,reason:'非下班時段'}});
assert.equal(d.querySelector('#pizza-level').textContent,'--');assert.ok(d.querySelector('#pizza-index').textContent.includes('資料不足'));
assert.ok(d.querySelector('#pizza-bars-line').textContent.includes('等待查詢時段'));}
{const w=d.defaultView;w.eval(fs.readFileSync('three-scenes.js','utf8'));
const st=w.pizzaOpenStates({pizza:[{name:'We, The Pizza',is_open:true,busyness:70},{name:'Extreme Pizza',is_open:false},{name:'Pizzato Pizza',is_open:null}],
  bars:{bars:[{name:'Crystal City Sports Pub',live_available:true,live_busyness:0},{name:'Highline RxR',open:'Closed'},{name:'Not Listed',live_available:true,live_busyness:9}]}});
assert.deepEqual(JSON.parse(JSON.stringify(st.count)),{pizza:{open:1,total:6},bars:{open:1,total:4},unknown:6,byHours:0,gone:[]});
assert.equal(st.states['Crystal City Sports Pub'].level,0); assert.equal(st.states['Extreme Pizza'].state,'closed'); assert.equal(st.states['Not Listed'],undefined);
w.renderPizzaBlock({pizza:[],pizza_summary:{state:'setup_needed'},bars:{available:false,off_hours:true,bars:[]}});
assert.equal(d.querySelector('#pz-3d-pizza').textContent,'0 / 6');assert.equal(d.querySelector('#pz-3d-bars').textContent,'0 / 4');
assert.ok(d.querySelector('#pz-3d-why').textContent.startsWith('10 家狀態未知：尚未在 BestTime 建檔'));
w.renderPizzaBlock({pizza:[],pizza_summary:{state:'off_hours'},bars:{available:false,off_hours:true,bars:[]}});
assert.ok(d.querySelector('#pz-3d-why').textContent.includes('非查詢時段'));}
{const w=d.defaultView;const wk=r=>Object.fromEntries([0,1,2,3,4,5,6].map(i=>[i,r]));
const vh={venues:{'We, The Pizza':{hours:wk([[660,1320]])},'Pizzato Pizza':{hours:wk([[960,1560]])},'Highline RxR':{permanently_closed:true,hours:wk([])}}};
const at=iso=>w.pizzaOpenStates({pizza:[],venue_hours:vh,bars:{bars:[]}},new Date(iso));
let st=at('2026-10-29T00:00:00Z');                    // Wed 20:00 in Washington
assert.equal(st.states['We, The Pizza'].state,'open');assert.equal(st.states['Pizzato Pizza'].state,'open');
assert.equal(st.count.pizza.open,2);assert.equal(st.count.bars.total,3);assert.deepEqual([...st.count.gone],['Highline RxR']);
st=at('2026-10-29T05:00:00Z');                        // Thu 01:00: only the shop open past midnight
assert.equal(st.states['We, The Pizza'].state,'closed');assert.equal(st.states['Pizzato Pizza'].state,'open');
st=w.pizzaOpenStates({pizza:[{name:'We, The Pizza',is_open:false}],venue_hours:vh},new Date('2026-10-29T00:00:00Z'));
assert.equal(st.states['We, The Pizza'].state,'closed');  // a live "Closed" beats the posted hours
w.renderPizzaBlock({pizza:[],pizza_summary:{state:'setup_needed'},venue_hours:vh,bars:{bars:[]}});
assert.ok(d.querySelector('#pz-3d-why').textContent.includes('Highline RxR 已永久停業'));
assert.ok(d.querySelector('#pz-3d-why').textContent.includes('依 Google 營業時間'));}
// Shop cards: without live readings they show posted hours and say foot traffic is missing; a live reading wins.
{const w=d.defaultView;const wk=r=>Object.fromEntries([0,1,2,3,4,5,6].map(i=>[i,r]));
const hrs=wk([[630,1320]]);
assert.equal(w.hoursLabel(hrs,new Date('2026-10-29T00:00:00Z')).text,'營業中 · 營業到 22:00');      // Wed 20:00 ET
assert.equal(w.hoursLabel(hrs,new Date('2026-10-29T05:00:00Z')).text,'已打烊 · 今天 10:30 開');     // Thu 01:00 ET
assert.equal(w.hoursLabel(hrs,new Date('2026-10-29T03:00:00Z')).text,'已打烊 · 明天 10:30 開');     // Wed 23:00 ET
assert.equal(w.hoursLabel(wk([[960,1560]]),new Date('2026-10-29T05:00:00Z')).text,'營業中 · 營業到 02:00');
assert.equal(w.hoursLabel({...wk([[600,1200]]),4:[]},new Date('2026-10-29T03:00:00Z')).text,'已打烊 · 週五 10:00 開');
assert.equal(w.hoursLabel(null),null);
w.renderPizzaShops([{name:'A',status:'setup_needed',is_open:null},{name:'B',status:'normal',is_open:true,busyness:40}],null,{venues:{A:{hours:wk([[0,1440]])},B:{hours:wk([])}}});
const cards=[...d.querySelectorAll('#pizza-shops-grid .pizza-shop')].map(c=>c.textContent);
assert.ok(cards[0].includes('營業中')&&cards[0].includes('人流資料尚未取得')&&!cards[0].includes('尚未建檔'));
assert.ok(cards[1].includes('正常')&&cards[1].includes('現在 40%'));
w.renderPizzaBlock({pizza:[],pizza_summary:{},bars:{available:false,setup_needed:true,bars:[]}});
assert.ok(d.querySelector('#pizza-bars-line').textContent.includes('尚未在 BestTime 建檔'));}
// Hourly bars: Washington weekday baseline (grey) + only today's live readings; 0 is drawn, yesterday is not.
{const w=d.defaultView,usual=Array(24).fill(null);usual[10]=40;usual[12]=80;
const shop={name:'x',recorded_at:'2026-10-27T16:06:00Z',usual_week:{'1':Array(24).fill(90),'2':usual},
 hourly_24h:[{at:'2026-10-26T20:00:00Z',v:90},{at:'2026-10-27T15:09:00Z',v:0},{at:'2026-10-27T14:09:00Z',v:null}]};
const box=d.createElement('div');box.innerHTML=w.pizzaHourlyChart(shop,'red');
const rects=[...box.querySelectorAll('rect')];
assert.equal(rects.filter(r=>r.getAttribute('fill')==='rgba(255,255,255,0.16)').length,2);
const live=rects.filter(r=>r.getAttribute('fill')==='red');
assert.equal(live.length,1);assert.equal(live[0].getAttribute('height'),'1.0');
assert.equal(rects.filter(r=>r.getAttribute('stroke-dasharray')).length,1);
assert.equal(w.pizzaHourlyChart({name:'y'},'red'),'');
// Before any live reading the usual curve still draws for the snapshot's day.
{const b2=d.createElement('div');b2.innerHTML=w.pizzaHourlyChart({name:'z',usual_week:{'2':usual}},'red','2026-10-27T16:06:00Z');assert.equal(b2.querySelectorAll('rect[fill="red"]').length,0);assert.equal(b2.querySelectorAll('rect[fill="rgba(255,255,255,0.16)"]').length,2);}
w.renderPizzaShops([{...shop,is_open:true,busyness:30,status:'quiet'}]);
assert.ok(d.querySelector('#pizza-hourly-legend').textContent.includes('週二'));
assert.equal(d.querySelectorAll('#pizza-shops-grid .pizza-hourly').length,1);}
d.defaultView.renderPizzaShops([{name:'b',busyness:45,usual_now:30,percentage_of_usual:150,status:'busy'},{name:'c',busyness:null,status:'setup_needed'},{name:'<i>',busyness:0,usual_now:20,percentage_of_usual:0,status:'quiet'}]);
{const t=d.querySelector('#pizza-shops-grid').textContent;assert.ok(t.includes('現在 45% · 平常 30% · 為平常的 150%'));assert.ok(t.includes('尚未建檔'));assert.ok(t.includes('現在 0%'));assert.equal(d.querySelector('#pizza-shops-grid i'),null);}

// Air activity: notices vs usual per region; missing stays missing, zero stays zero, closure wins the summary.
{const w=d.defaultView,sum=()=>d.querySelector('#air-summary').textContent,rows=()=>d.querySelector('#air-regions').textContent;
const regions=[{key:'taiwan',name:'台海',factors:{notam_danger:20,notam_baseline:20.1,avi_count:0}},
 {key:'korea',name:'朝鮮半島',factors:{avi_count:1}},
 {key:'mideast',name:'美伊 / 中東',factors:{notam_danger:12,notam_baseline:0,avi_count:null}}];
w.renderAirActivity({regions,notams:{korea:{stale:true,observed_at:new Date().toISOString()}},aviation:{summary:{total:444}}});
assert.ok(sum().includes('美伊 / 中東的危險公告明顯多於平常'));assert.ok(sum().includes('444'));
assert.ok(rows().includes('跟平常差不多'));assert.ok(rows().includes('無新鮮完整資料'));assert.ok(rows().includes('資料較舊'));
assert.ok(rows().includes('0 架'));assert.ok(!rows().includes('null'));
w.renderAirActivity({regions:[{...regions[0],factors:{...regions[0].factors,notam_closure:true}}],notams:{}});
assert.ok(sum().includes('有領空關閉公告'));
w.renderAirActivity({regions:[regions[1]],notams:{}});assert.ok(sum().includes('資料不足'));
w.renderAirActivity({});assert.ok(sum().includes('暫停判讀'));assert.equal(d.querySelector('#air-regions').textContent,'');
assert.equal(w.airCompare(3,0),'up');assert.equal(w.airCompare(2,0),'same');assert.equal(w.airCompare(0,6),'down');assert.equal(w.airCompare(null,5),null);
assert.ok(d.querySelector('#air-card #avi-list'),'aircraft list lives inside the air card');}
assert.equal(d.querySelector('#observation-overview'),null);
assert.ok(!d.body.textContent.includes('分項觀察'));
assert.ok(!d.querySelector('#ticker').textContent.includes('披薩指數'));
assert.ok(!d.querySelector('#ticker').textContent.includes('戰爭壓力指數'));
assert.ok(!d.querySelector('#ticker').textContent.includes('WPI'));
const siblingHrefs=['https://hypeboss.cc/','https://stocktools.cc/','https://toolist.cc/','https://simples.com.tw/'];
for(const href of siblingHrefs){
  const links=[...d.querySelectorAll(`a[href="${href}"]`)];
  assert.ok(links.length>=1, href+' missing from dashboard');
  assert.ok(links.every(a=>a.target==='_blank' && a.rel==='noopener'));
}
assert.ok(d.querySelector('header a[href="https://hypeboss.cc/"]'));
assert.ok(d.querySelector('header a[href="https://stocktools.cc/"]'));
assert.ok(d.querySelector('header a[href="https://toolist.cc/"]'));
assert.ok(d.querySelector('footer a[href="https://stocktools.cc/"]'));
assert.ok(d.querySelector('footer a[href="https://toolist.cc/"]'));
assert.ok(d.querySelector('footer a[href="https://simples.com.tw/"]'));
assert.ok(d.querySelector('footer').textContent.includes('SIMPLES 工具網'));
assert.ok(d.querySelector('footer').textContent.includes('Stocktools'));
assert.ok(d.querySelector('footer').textContent.includes('Toolist'));
const hypeLinks=[...d.querySelectorAll('a[href="https://hypeboss.cc/"]')];
assert.ok(hypeLinks.length>=2);
assert.ok(hypeLinks.every(a=>a.textContent.includes('HypeBoss') && !/Crypig/i.test(a.textContent)));
assert.ok(![...d.querySelectorAll('a')].some(a=>/opensky-network\.org/i.test(a.href)));
const stocktoolsDeep=['https://www.stocktools.cc/tw/us-fee-calculator','https://www.stocktools.cc/tw/us-etf','https://www.stocktools.cc/tw/us-deposit','https://www.stocktools.cc/tw/us-open-account','https://www.stocktools.cc/tw/us-dividend','https://www.stocktools.cc/tw/us-first-buy','https://www.stocktools.cc/tw/us-premarket','https://www.stocktools.cc/tw/us-order-types','https://www.stocktools.cc/tw/us-adr','https://www.stocktools.cc/tw/us-fx','https://www.stocktools.cc/tw/us-fractional','https://www.stocktools.cc/tw/us-earnings'];
for(const href of stocktoolsDeep){
  const links=[...d.querySelectorAll(`a[href="${href}"]`)];
  assert.ok(links.length>=2, href+' should appear in footer and finance tools');
  assert.ok(links.every(a=>a.target==='_blank' && a.rel==='noopener'));
  assert.ok(d.querySelector(`footer a[href="${href}"]`));
  assert.ok(d.querySelector(`#related-tools-fin a[href="${href}"]`));
}
assert.ok(d.querySelector('footer .network-links[aria-label="相關工具"]'));
assert.ok(!d.body.textContent.includes('Moneytools'));
assert.ok(![...d.querySelectorAll('a')].some(a=>/moneytools|firstrade|luxstay/i.test(a.href)));

if(mode==='valid'){{const list=d.getElementById('news-list');const kept=list.innerHTML;list.innerHTML='';for(let i=0;i<12;i++){const x=d.createElement('div');x.textContent='n'+i;list.appendChild(x);}await new Promise(r=>setTimeout(r,0));const btn=list.nextElementSibling;assert.equal(btn.className,'clamp-more');assert.equal(btn.textContent,'顯示全部（共 12 則）');btn.click();assert.ok(list.classList.contains('expanded'));assert.equal(btn.textContent,'收合');list.innerHTML='<div>a</div>';await new Promise(r=>setTimeout(r,0));assert.equal(btn.hidden,true);list.classList.remove('expanded');list.innerHTML=kept;}{const rows=d.querySelectorAll('.usda-row');assert.equal(rows.length,1);assert.ok(rows[0].textContent.includes('0 千噸'));assert.ok(!rows[0].textContent.includes('2026-10-15'));assert.equal(d.querySelector('.usda-none').textContent,'小麥、玉米：本期沒有美對中銷售觀測（不等於零）');}assert.ok(/有效權重覆蓋 65%（暫缺：[^）]*新聞強度[^）]*；熱異常不計分）/.test(d.querySelector('#html-wpi-updated').textContent),d.querySelector('#html-wpi-updated').textContent);assert.equal(d.querySelector('#hero-wpi-basis').textContent,'由 5 / 6 項計算 · 缺新聞強度');assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('170 架'));assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('異常分數 0'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('11,785 筆'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('暫不計分'));assert.ok(d.querySelector('#poly-list-container').textContent.includes('美國會在12月31日前打擊古巴嗎？'));assert.ok(d.querySelector('#news-list').textContent.includes('新聞繁體中文標題'));assert.ok(!d.querySelector('#news-list').textContent.includes('English original'));assert.ok(d.querySelector('#strat-grid').textContent.includes('最近歷史參考：2026-06'));assert.ok(d.querySelector('#sh-svg').textContent.includes('缺報'));assert.ok(!d.querySelector('#sh-svg').innerHTML.includes('999'));}

if(mode==='valid'){
 const w=dom.window;
 const cases=[
  {key:'ukraine',name:'俄烏',flag:'',score:null,level:'INSUFFICIENT_DATA',factors:{poly:69.6,notam:0}},
  {key:'taiwan',name:'台海',flag:'',score:null,level:'INSUFFICIENT_DATA',factors:{poly:6.6}},
  {key:'korea',name:'朝鮮',flag:'',score:null,level:'INSUFFICIENT_DATA',factors:{notam:0}},
  {key:'empty',name:'缺值',flag:'',score:null,level:'INSUFFICIENT_DATA',factors:{poly:null,gdelt:NaN,notam:false,firms_hotspots:300,avi_count:20}}
 ];
 const original=JSON.stringify(cases);
 assert.equal(w.regionalObservation(cases[0]).score,48.7);
 assert.equal(w.regionalObservation(cases[1]).score,6.6);
 assert.equal(w.regionalObservation(cases[2]).score,0);
 assert.equal(w.regionalObservation(cases[3]).score,null);
 assert.equal(w.regionalObservation({...cases[1],score:32}).score,32,'qualified historical model score is preserved');
 assert.equal(w.regionalObservation({...cases[1],factors:{poly:Infinity,notam:-1,gdelt:101}}).score,null);
 w.renderRegions(cases);
 const board=d.querySelector('#region-board');
 assert.ok(board.textContent.includes('單一來源觀測'));
 assert.ok(!board.textContent.includes('資料有限'),'caveat shown once under the board, not on every card');
 assert.ok(board.parentElement.textContent.includes('資料有限，不是整體風險'));
 assert.ok(board.textContent.includes('尚無有效計分資料'));
 assert.ok(!board.textContent.includes('參考（不計分）'),'aircraft/heat reference line removed; aircraft live in the air card');
 assert.ok(!board.textContent.includes('INSUFFICIENT_DATA'));
 assert.ok(!board.textContent.includes('CRITICAL'));
 assert.equal(JSON.stringify(cases),original,'presentation must not rewrite snapshot or historical scores');
 // Stale/legacy load path clears factors before rendering; no observation score survives.
 w.renderRegions(cases.map(r=>({...r,score:null,factors:{}})));
 assert.ok(!board.textContent.includes('單一來源觀測'));
}

if(mode==='valid'){
  const w=dom.window;
  const sparse=Array.from({length:36},(_,i)=>({ym:`${2023+Math.floor(i/12)}-${String(i%12+1).padStart(2,'0')}`,schema_version:2,src:'mirror','4001':i===2?0:i===3?4:null}));
  const preserved=JSON.stringify(sparse);
  w.SH_STATE.range=36;w.renderStratHistory({strat_hist:sparse});
  assert.equal(d.querySelectorAll('#sh-svg .fh-missing').length,34,'missing months remain distinct');
  assert.equal(d.querySelectorAll('#sh-svg .fh-zero').length,1,'reported zero remains visible');
  assert.ok(![...d.querySelectorAll('#sh-svg text')].some(x=>x.textContent.includes('缺報')),'no repeated axis labels');
  assert.equal(d.querySelectorAll('#sh-svg [data-tip]').length,36,'each month remains inspectable');
  assert.equal(JSON.stringify(sparse),preserved,'history is unchanged');
  assert.equal(d.querySelector('#sh-legend details').open,false,'long explanation starts collapsed');
  assert.ok(d.querySelector('#sh-legend').textContent.includes('缺報'));
  assert.ok(d.querySelector('.live-lbl').textContent.includes('備份'));
  const accepted=w.eval('DATA_UPDATED_AT');
  // Use the snapshot clock; skip missing/malformed values but retain real zero.
  const snapshot=new Date(Date.now()-5*3600000).toISOString();
  w.eval(`DATA_UPDATED_AT = ${JSON.stringify(snapshot)}`);
  assert.equal(w._mdVal({fin:{risk_off_cluster:0}},'cluster'),null);
    w.renderFinanceSnapshot({'GC=F':{chg:1},'BZ=F':{chg:-1},LMT:{chg:1},RTX:{chg:-1},NOC:{chg:0}});
  for(const id of ['html-fin-gc-chg','html-stk-lmt-c'])assert.ok(d.getElementById(id).classList.contains('up'));
  for(const id of ['html-fin-bz-chg','html-stk-rtx-c'])assert.ok(d.getElementById(id).classList.contains('down'));
  assert.ok(!d.getElementById('html-stk-noc-c').classList.contains('up'));
  w.renderFinanceSnapshot({});assert.ok(!d.getElementById('html-fin-gc-chg').classList.contains('up'));

  assert.equal(w._mdVal({fin:{risk_off_cluster:0,risk_off_observed:6}},'cluster'),0);
  assert.equal(w._mdVal({fin:{risk_off_cluster:2,risk_off_observed:5}},'cluster'),null);
  const insight={version:1,as_of:new Date().toISOString(),activity:{status:'within_baseline',baseline_days:20,median:10,latest:{date:'2026-09-13',aircraft:0,ships:5,period_end:new Date().toISOString(),source_url:'https://air.mnd.gov.tw/TW/News/News_Detail.aspx?CID=213&ID=1'}},news:{sample_24h:2,publishers_24h:1},markets:[{slug:'test',question:'English title',question_zh:'台海市場中文問題',yes_percent:10,delta_pp:3,comparison_hours:24,comparison_at:new Date(Date.now()-24*3600000).toISOString(),end_date:'2030-01-01T00:00:00Z'}],timeline:[{at:new Date().toISOString(),title:'測試新聞',time_label:'新聞發稿時間',url:'javascript:alert(1)'}]};
  w.renderTaiwanInsight({taiwan_insight:insight});
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('共機 0 架次'));
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('+3 個百分點'));
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('台海市場中文問題'));
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('有限樣本'));
  assert.ok(d.querySelector('#taiwan-insight-body .ti-market-section .ti-markets'));
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('2030'));
  // No history → no chart; a 30-day history → line, change and range; malformed points are dropped, not zeroed.
  assert.equal(d.querySelector('#taiwan-insight-body .ti-trend'),null);
  w.renderTaiwanInsight({taiwan_insight:{...insight,markets:[{...insight.markets[0],history_30d:[{at:'2026-09-29T00:00:00Z',p:12.5},{at:'bad',p:50},{at:'2026-10-10T00:00:00Z',p:-3},{at:'2026-10-15T00:00:00Z',p:8},{at:'2026-10-28T00:00:00Z',p:9.5}]}]}});
  {const tr=d.querySelector('#taiwan-insight-body .ti-trend');assert.ok(tr);const t=tr.textContent.replace(/\s+/g,' ');
   assert.ok(t.includes('近 29 天走勢'),t);assert.ok(t.includes('-3 個百分點'),t);assert.ok(t.includes('最低 8% · 最高 12.5%'),t);assert.ok(t.includes('現在 9.5%'),t);
   assert.equal(tr.querySelector('polyline').getAttribute('points').split(' ').length,3);}
  w.renderTaiwanInsight({taiwan_insight:{...insight,markets:[{...insight.markets[0],history_30d:[{at:'2026-10-28T00:00:00Z',p:9.5}]}]}});
  assert.equal(d.querySelector('#taiwan-insight-body .ti-trend'),null);
  w.renderTaiwanInsight({taiwan_insight:insight});

  // Missing fields must not invent zero, dates, or a comparable market change.
  const ti=()=>d.querySelector('#taiwan-insight-body').textContent;
  w.renderTaiwanInsight({taiwan_insight:{...insight,news:{},activity:{...insight.activity,median:null,latest:{...insight.activity.latest,ships:null,government_ships:0}}}});
  assert.ok(ti().includes('共艦 缺資料 艘、公務船 0 艘'));
  assert.ok(ti().includes('中位數 缺資料'));
  assert.ok(ti().includes('樣本：缺資料 則、缺資料 個'));
  assert.ok(ti().includes('時間缺資料'));
  assert.ok(!ti().includes('1970'));
  const savedAt=new Date(Date.now()-2*3600000).toISOString();
  w.renderTaiwanInsight({taiwan_insight:{...insight,news:{input_status:'stale',sample_24h:0,publishers_24h:0,latest_at:savedAt}}});
  assert.ok(ti().includes('沿用舊樣本'));
  assert.ok(ti().includes('樣本：0 則、0 個'));
  assert.ok(ti().includes('發稿時間'));
  w.renderTaiwanInsight({source_health:{tw_news:{status:'unavailable'}},taiwan_insight:{...insight,news:{sample_24h:2,publishers_24h:1}}});
  assert.ok(ti().includes('未取得有效樣本，不代表沒有新聞'));
  assert.ok(ti().includes('樣本：2 則、1 個'));
  for(const value of [null,undefined,-1,'0',NaN]){
    w.renderTaiwanInsight({taiwan_insight:{...insight,news:{sample_24h:value,publishers_24h:value}}});
    assert.ok(ti().includes('樣本：缺資料 則、缺資料 個'));
  }
  const market=insight.markets[0];
  for(const [extra,message] of [
    [{yes_percent:null},'報價缺資料'],
    [{yes_percent:'0'},'報價缺資料'],
    [{yes_percent:101},'報價缺資料'],
    [{end_date:null},'截止時間缺資料'],
    [{end_date:new Date(Date.now()-1000).toISOString()},'題目已到期'],
    [{comparison_at:null},'缺少可核對時間'],
    [{comparison_at:new Date(Date.now()-30*3600000).toISOString()},'缺少可核對時間'],
    [{delta_pp:NaN},'缺少可核對時間']
  ]){
    w.renderTaiwanInsight({taiwan_insight:{...insight,markets:[{...market,...extra}]}});
    assert.ok(ti().includes(message));
    assert.ok(!ti().includes('+3 個百分點'));
  }
  w.renderTaiwanInsight({taiwan_insight:{...insight,markets:[{...market,yes_percent:0,delta_pp:0}]}});
  assert.ok(ti().includes('YES 報價 0%'));
  assert.ok(ti().includes('0 個百分點'));
  assert.ok(ti().includes('比較基準時間'));
  assert.ok(ti().includes('報價快照時間'));
  w.renderTaiwanInsight({taiwan_insight:insight});
  assert.equal(d.querySelector('#taiwan-insight-timeline a'),null);
  w.renderTaiwanInsight({taiwan_insight:{...insight,as_of:new Date(Date.now()-7*3600000).toISOString()}});
  assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('過期'));
  assert.equal(d.querySelector('#taiwan-insight-timeline').textContent,'');
  w.renderTaiwanInsight({});assert.ok(d.querySelector('#taiwan-insight-body').textContent.includes('等待'));
  const originalRegions=w.eval('OBSERVED_DATA.regions');
  w.eval("OBSERVED_DATA.regions = [{key:'taiwan',factors:{poly:20,gdelt:0}}]");
  const basis={combined:['p','a','z','s','w'],regions:{taiwan:['poly','gdelt']}};
  const row=(hours,value,model='wpi-4.0')=>({ts:new Date(Date.parse(snapshot)-hours*3600000).toISOString(),model_version:model,combined:value,regions:{taiwan:value},score_basis:basis});
  const history=rows=>w.eval(`WW_HISTORY = ${JSON.stringify(rows)}`);
  history([row(24,10),row(19,90)]);
  assert.ok(w.trendArrow(20,'taiwan').includes('▲+10'));
  assert.ok(w.trendArrow(20,'taiwan').includes('24.0 小時'));
  history([row(24,null),row(23,0),row(24,90,'legacy'),row(24,'80')]);
  assert.ok(w.trendArrow(20,'taiwan').includes('▲+20'));
  assert.equal(w.trendArrow('20','taiwan'),'');
  history([row(29,10),row(-1,10)]);assert.equal(w.trendArrow(20,'taiwan'),'');
  history([{...row(24,10),score_basis:null}]);assert.equal(w.trendArrow(20,'taiwan'),'');
  history([{...row(24,10),score_basis:{regions:{taiwan:['poly','notam']}}}]);
  assert.equal(w.trendArrow(20,'taiwan'),'');
  history([{...row(24,10),score_basis:{regions:{taiwan:['gdelt','poly']}}}]);
  assert.ok(w.trendArrow(20,'taiwan').includes('▲+10'));
  history([row(24,20)]);assert.ok(w.trendArrow(20).includes('→'));
  w.eval(`DATA_UPDATED_AT = ${JSON.stringify(new Date(Date.now()-7*3600000).toISOString())}`);
  assert.equal(w.trendArrow(20),'');
  w.eval(`DATA_UPDATED_AT = ${JSON.stringify(accepted)}; WW_HISTORY = []; OBSERVED_DATA.regions = ${JSON.stringify(originalRegions)}`);


  const older={...data,updated_at:new Date(Date.parse(accepted)-3600000).toISOString(),score:{...data.score,combined_score:99}};
  w.fetch=async(url)=>({ok:true,json:async()=>String(url).includes('data.json')?older:[]});
  await w.fetchRealPizzaData();
  assert.equal(w.eval('DATA_UPDATED_AT'),accepted);
  assert.equal(w.htmlWpiCalc(),42);
  assert.ok(d.querySelector('#last-update-ts').textContent.includes('未覆蓋'));
  // An older response completing after a newer request must not win the race.
  let releaseOld;
  let first=true;
  const newer={...data,updated_at:new Date().toISOString()};
  w.fetch=async(url)=>{
    if(!String(url).includes('data.json'))return {ok:true,json:async()=>[]};
    if(first){first=false;return new Promise(resolve=>{releaseOld=()=>resolve({ok:true,json:async()=>older})});}
    return {ok:true,json:async()=>newer};
  };
  const pending=w.fetchRealPizzaData();
  await w.fetchRealPizzaData();
  releaseOld();await pending;
  assert.equal(w.eval('DATA_UPDATED_AT'),newer.updated_at);
  assert.equal(w.htmlWpiCalc(),42);
  assert.ok(d.querySelector('#last-update-ts').textContent.includes('未覆蓋'));

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
if(mode==='valid'){
 const sample={food_hist:[{ym:'2026-06',soy:10,wheat:20,corn:30,us_soy:2,us_wheat:3,us_corn:4},{ym:'2026-07',soy:11,wheat:21,corn:31,us_soy:2,us_wheat:3,us_corn:4}],usda:{schema_version:2,hist:{soy:[{w:'2026-08-01',market_year:2026,commit:10},{w:'2026-08-08',market_year:2026,commit:12}],wheat:[],corn:[]}}};
 const original=JSON.stringify(sample);
 dom.window.renderFoodHistory(sample);dom.window.renderUsdaHist(sample);dom.window.renderGrainExplorer(sample);
 assert.equal(d.querySelector('#uh-wrap').hidden,true);
 d.querySelector('#grain-view [data-view="commit"]').click();
 assert.equal(d.querySelector('#food-hist-wrap').hidden,true);
 assert.equal(d.querySelector('#uh-wrap').hidden,false);
 assert.ok(d.querySelector('#uh-legend').textContent.includes('千噸'));
 d.querySelector('#grain-cmd [data-cmd="wheat"]').click();
 assert.ok(d.querySelector('#uh-svg').textContent.includes('資料累積中'));
 d.querySelector('#grain-view [data-view="vol"]').click();
 assert.equal(d.querySelector('#food-hist-wrap').hidden,false);
 assert.equal(d.querySelector('#uh-wrap').hidden,true);
 assert.equal(dom.window.FH_STATE.cmd,'wheat');
 assert.equal(dom.window.UH_STATE.cmd,'wheat');
 assert.equal(JSON.stringify(sample),original);
}
if(mode==='valid'){
 const w=dom.window;
 assert.equal(w.mdWindow(1,new Date('2024-03-31T04:00:00Z')).start,'2024-02-29');
 const win=w.mdWindow(1), old=new Date(win.start+'T00:00:00Z');old.setUTCDate(old.getUTCDate()-1);
 const future=new Date(win.end+'T00:00:00Z');future.setUTCDate(future.getUTCDate()+1);
 const ds={};ds[old.toISOString().slice(0,10)]={fin:{oil_premium:123}};
 ds[win.start]={fin:{oil_premium:0}};ds[win.end]={fin:{oil_premium:-5}};
 ds[future.toISOString().slice(0,10)]={fin:{oil_premium:1000}};
 w.MD_JSON={days:ds};w.MD_STATE={key:'oil_premium',months:1};const saved=JSON.stringify(ds);w.renderMetricsHist();
 assert.equal(d.querySelectorAll('#md-svg circle').length,2);
 assert.ok(d.querySelector('#md-period').textContent.includes(win.start));
 d.querySelector('#md-range [data-months="3"]').click();
 assert.equal(w.MD_STATE.key,'oil_premium');assert.equal(d.querySelectorAll('#md-svg circle').length,3);
 d.querySelector('#md-range [data-months="12"]').click();
 assert.equal(w.MD_STATE.months,12);assert.equal(d.querySelectorAll('#md-svg circle').length,3);
 assert.equal(JSON.stringify(ds),saved);
 // Cluster: valid zero stays visible, missing calendar days are marked (not zero), axis ticks are integers.
 const cd=new Date(win.end+'T00:00:00Z'),day=k=>{const x=new Date(cd);x.setUTCDate(x.getUTCDate()-k);return x.toISOString().slice(0,10);};
 const cs={};cs[day(4)]={fin:{risk_off_cluster:2,risk_off_observed:6}};cs[day(3)]={fin:{risk_off_cluster:0,risk_off_observed:6}};
 cs[day(0)]={fin:{risk_off_cluster:1,risk_off_observed:6}};
 w.MD_JSON={days:cs};w.MD_STATE={key:'cluster',months:1};w.renderMetricsHist();
 assert.equal(d.querySelectorAll('#md-svg rect.md-zero').length,1);
 assert.equal(d.querySelectorAll('#md-svg rect.md-missing').length,2);
 assert.ok(d.querySelector('#md-legend').textContent.includes('缺紀錄 2 天'));
 assert.deepEqual([...d.querySelectorAll('#md-svg text.fh-svg-axis')].map(t=>t.textContent).filter(t=>/^\d+$/.test(t)),['6','5','4','3','2','1','0']);
}
assert.equal(result.wpi,mode==='valid'?'42':'--');dom.window.close();
}})().catch(e=>{console.error(e);process.exit(1)});
