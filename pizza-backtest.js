/* Presentation only: no source requests, notification calls or client-side outcomes. */
(() => {
  'use strict';
  let report=null, threshold='3';
  const words={
    title:['披薩訊號 · 48 小時追蹤','Pizza signals · 48-hour follow-up'],
    subtitle:['實驗回測｜不是美軍官方 DEFCON','Experimental study | Not official US military DEFCON'],
    broad:['DEFCON 3／2／1','DEFCON 3 / 2 / 1'], strict:['DEFCON 2／1','DEFCON 2 / 1'],
    loading:['回測資料尚未載入','Study data has not loaded'],
    unknown:['準確率尚不能估計','Hit rate not yet estimable'],
    mature:['成熟窗口符合行動比例','Qualifying-action fraction in mature windows'],
    caveat:['未核實不當成沒有行動','Unverified does not mean no action'],
    cutoff:['資料截至','Data cutoff'], observations:['份快照','snapshots'],
    error:['部分封存無法讀取，比例暫停顯示','Some archives are unreadable; rate withheld']
  };
  const en=()=>window.WarhubI18n?.language==='en';
  const t=k=>words[k]?.[en()?1:0]||k;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=v=>{const n=new Date(v);return Number.isFinite(n.getTime())?n.toISOString().replace('T',' ').slice(0,16)+' UTC':'—';};
  const num=n=>Number.isInteger(n)&&n>=0?n:'—';
  // One plain sentence instead of four mostly-zero boxes; every count stays visible.
  function summary(g){
    const c=g.counts||{}, lvl=threshold==='3'?'3':'2', odd=c.uncertain_start>0;
    return en()
      ? `Reached DEFCON ${lvl} or tighter ${num(g.detected_crossings)} times: ${num(c.reviewed_yes)} confirmed action, ${num(c.reviewed_no)} reviewed with none found, ${num(c.unreviewed)} still uncertain, ${num(c.pending)} inside the 48-hour window${odd?`; ${num(c.uncertain_start)} with unknown start excluded`:''}.`
      : `升到 DEFCON ${lvl} 或更緊張共 ${num(g.detected_crossings)} 次：確認有行動 ${num(c.reviewed_yes)} 次、核對後沒有 ${num(c.reviewed_no)} 次、仍不確定 ${num(c.unreviewed)} 次、未滿 48 小時 ${num(c.pending)} 次${odd?`；另有 ${num(c.uncertain_start)} 次起點不明，不納入`:''}。`;
  }
  function draw(){
    const host=document.getElementById('pizza-backtest');if(!host)return;
    const g=report?.groups?.[threshold];
    const tabs=['3','2'].map(n=>`<button type="button" data-pizza-threshold="${n}" aria-pressed="${n===threshold}">${t(n==='3'?'broad':'strict')}</button>`).join('');
    let body=`<p>${t('loading')}</p>`;
    if(g){
      const rate=typeof g.rate==='number'&&Number.isFinite(g.rate)&&g.rate>=0&&g.rate<=1&&!report.unreadable_archives?g.rate:null;
      body=`<div class="pizza-study-rate"><strong>${rate===null?t('unknown'):(rate*100).toFixed(1)+'%'}</strong>${rate===null?'':`<span>${t('mature')}</span>`}</div><p class="pizza-study-summary">${esc(summary(g))}</p><p class="pizza-study-cutoff">${t('cutoff')}: ${date(report.as_of)} · ${esc(report.observations)} ${t('observations')} · ${t('caveat')}${report.unreadable_archives?' · '+t('error'):''}</p>`;
    }
    host.innerHTML=`<div class="pizza-study-heading"><div><h3>${t('title')}</h3><p>${t('subtitle')}</p></div><div class="pizza-study-tabs" aria-label="DEFCON">${tabs}</div></div>${body}`;
    host.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{threshold=b.dataset.pizzaThreshold;draw();}));
  }
  window.renderPizzaBacktest=function(value){
    if(value?.version!=='pizza-48h-v1'||!value.groups?.['3']||!value.groups?.['2']||!Number.isFinite(Date.parse(value.as_of)))return;
    if(report&&Date.parse(value.as_of)<Date.parse(report.as_of))return;
    report=value;draw();
  };
  function start(){draw();fetch('/research/pizza-backtest.json').then(r=>{if(!r.ok)throw Error('Study unavailable');return r.json();}).then(window.renderPizzaBacktest).catch(()=>{});}
  document.addEventListener('warhub-language-change',draw);
  document.addEventListener('warhub-i18n-ready',draw);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
