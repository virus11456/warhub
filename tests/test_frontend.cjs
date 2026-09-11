process.chdir(require('path').resolve(__dirname,'..'));
const {JSDOM,VirtualConsole}=require('jsdom');const fs=require('fs');const assert=require('assert');
(async()=>{for(const mode of ['missing','legacy','new','valid']){
 const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>{if(!e.message.includes('Not implemented'))errors.push(e.message)});vc.on('warn',(...m)=>{if(String(m).includes('render error'))errors.push(m.join(' '))});
 const data=JSON.parse(fs.readFileSync('tests/fixtures/legacy-data.json'));
 if(['new','valid'].includes(mode)){data.updated_at=new Date().toISOString();data.score={model_version:'wpi-4.0',combined_score:mode==='valid'?42:null,coverage:.65,factors:{p:30,a:20,g:null,z:40,f:null,s:40,w:25},alert_level:'MODERATE'};data.regions=data.regions.map(r=>({...r,score:null,level:'INSUFFICIENT_DATA',coverage:0,factors:{}}));data.source_health={test:{label:'GDELT',status:'stale',note:'舊資料不計分'}};}
 if(mode==='valid'){data.news=[{title:'English original',title_zh:'新聞繁體中文標題',url:'https://example.com/news',ts:data.updated_at}];data.strat={schema_version:2,ref_month:'2026-07',items:[{cmd:'4001',name:'天然橡膠',wan_ton:null,incomplete:true,reporters:0}]};data.strat_hist=[{ym:'2026-06',src:'mirror','4001':2.2},{ym:'2026-07',schema_version:2,src:'mirror','4001':null}];}
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
if(mode==='valid'){assert.ok(d.querySelector('#news-list').textContent.includes('新聞繁體中文標題'));assert.ok(!d.querySelector('#news-list').textContent.includes('English original'));assert.ok(d.querySelector('#strat-grid').textContent.includes('最近歷史參考：2026-06'));assert.ok(d.querySelector('#sh-svg').textContent.includes('缺報'));}
assert.equal(result.wpi,mode==='valid'?'42':'--');dom.window.close();
}})().catch(e=>{console.error(e);process.exit(1)});
