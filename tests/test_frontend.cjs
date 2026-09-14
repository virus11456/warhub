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
const experimental=d.querySelector('#experimental-observations');
assert.ok(experimental && !experimental.open);
assert.equal(experimental.parentElement.className,'container');
for(const selector of ['#pizza-card','.hero-strip','.wpi-section']) {
  assert.equal(d.querySelectorAll(selector).length,1);
  assert.ok(experimental.contains(d.querySelector(selector)));
}
assert.equal(d.querySelector('#observation-overview').querySelectorAll('h3').length,4);
for(const a of d.querySelectorAll('#observation-overview a')) assert.ok(d.querySelector(a.getAttribute('href')));
assert.ok(!d.querySelector('#ticker').textContent.includes('披薩指數'));
assert.ok(!d.querySelector('#ticker').textContent.includes('戰爭壓力指數'));
assert.ok(!d.querySelector('#ticker').textContent.includes('WPI'));

if(mode==='valid'){assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('170 架'));assert.ok(d.querySelector('#html-wpi-a-desc').textContent.includes('異常分數 0'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('11,785 筆'));assert.ok(d.querySelector('#html-wpi-f-desc').textContent.includes('暫不計分'));assert.ok(d.querySelector('#poly-list-container').textContent.includes('美國會在12月31日前打擊古巴嗎？'));assert.ok(d.querySelector('#news-list').textContent.includes('新聞繁體中文標題'));assert.ok(!d.querySelector('#news-list').textContent.includes('English original'));assert.ok(d.querySelector('#strat-grid').textContent.includes('最近歷史參考：2026-06'));assert.ok(d.querySelector('#sh-svg').textContent.includes('缺報'));assert.ok(!d.querySelector('#sh-svg').innerHTML.includes('999'));}
if(mode==='valid'){
  const w=dom.window;
  assert.ok(d.querySelector('.live-lbl').textContent.includes('備份'));
  w.renderNotacObservation({notams:{taiwan:{provider:'NOTAC',complete:true,total:0,danger:0,observed_at:new Date().toISOString(),firs:['RCAA']}}});
  assert.ok(d.querySelector('#notac-body').textContent.includes('有效公告 0 筆'));
  w.renderNotacObservation({notams:{taiwan:{provider:'NOTAC',stale:true,observed_at:'2020-01-01T00:00:00Z',latest_attempt:{partial:true,sample_count:20,reported_count:100}}}});
  assert.ok(d.querySelector('#notac-body').textContent.includes('已取得樣本 20 筆'));
  assert.ok(!d.querySelector('#notac-body').textContent.includes('有效公告 0 筆'));
  assert.ok(d.querySelector('#notac-body').textContent.includes('2020'));
  w.renderNotacObservation({notams:{taiwan:{provider:'NOTAC',complete:true,total:5,danger:1,observed_at:'2020-01-01T00:00:00Z'}}});
  assert.ok(!d.querySelector('#notac-body').textContent.includes('有效公告 5 筆'));
  const accepted=w.eval('DATA_UPDATED_AT');
  // Use the snapshot clock; skip missing/malformed values but retain real zero.
  const snapshot=new Date(Date.now()-5*3600000).toISOString();
  w.eval(`DATA_UPDATED_AT = ${JSON.stringify(snapshot)}`);
  assert.equal(w._mdVal({fin:{risk_off_cluster:0}},'cluster'),null);
  assert.equal(w._mdVal({fin:{risk_off_cluster:0}},'cluster_legacy'),0);
  assert.equal(w._mdVal({fin:{risk_off_cluster:2,risk_off_observed:6}},'cluster_legacy'),null);
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

  // Missing combined scores must not erase valid regional observations or bridge gaps.
  const chartRow=(hours,value,regional=value,keys=['p','a','z'])=>({
    ts:new Date(Date.parse(accepted)-hours*3600000).toISOString(),model_version:'wpi-4.0',
    combined:value,regions:{taiwan:regional},score_basis:{combined:keys,regions:{taiwan:['poly','gdelt']}}});
  const chartRegions=[{key:'taiwan',flag:'',name:'台海'}];
  history([chartRow(10,0),chartRow(8,10),chartRow(6,null,30),chartRow(4,20),chartRow(2,30),chartRow(200,99)]);
  w.renderTrendChart(chartRegions);
  let chart=d.querySelector('#trend-chart');
  assert.equal(chart.querySelectorAll('rect[data-tip]').length,5);
  assert.equal(chart.querySelectorAll('polyline').length,3); // two combined segments + continuous region
  assert.ok(chart.innerHTML.includes('缺資料'));
  assert.ok(chart.querySelector('polyline').getAttribute('points').includes(',132.0')); // true zero
  history([chartRow(16,10),chartRow(14,20),chartRow(4,30),chartRow(2,40)]);
  w.renderTrendChart([]);assert.equal(chart.querySelectorAll('polyline').length,2);
  history([chartRow(8,10),chartRow(6,20),chartRow(4,30,30,['p','g','z']),chartRow(2,40,40,['p','g','z'])]);
  w.renderTrendChart([]);assert.equal(chart.querySelectorAll('polyline').length,2);
  history([8,6,4,2].map(h=>({...chartRow(h,20),score_basis:null})));
  w.renderTrendChart([]);assert.equal(chart.querySelectorAll('polyline').length,0);
  assert.equal(chart.querySelectorAll('circle').length,4);
  history([]);w.renderTrendChart([]);
  assert.equal(chart.querySelector('svg'),null);assert.equal(d.querySelector('#trend-legend').textContent,'');

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
assert.equal(result.wpi,mode==='valid'?'42':'--');dom.window.close();
}})().catch(e=>{console.error(e);process.exit(1)});
