/* Presentation only: no source requests, notification calls or client-side outcomes. */
(() => {
  'use strict';
  let report=null, threshold='3';
  const words={
    title:['披薩訊號 · 48 小時追蹤','Pizza signals · 48-hour follow-up'],
    subtitle:['實驗回測｜不是美軍官方 DEFCON','Experimental study | Not official US military DEFCON'],
    broad:['DEFCON 3／2／1','DEFCON 3 / 2 / 1'], strict:['DEFCON 2／1','DEFCON 2 / 1'],
    rate:['完整核實後才顯示比例','Rate withheld until all mature windows are reviewed'],
    loading:['回測資料尚未載入','Study data has not loaded'],
    crossings:['觀測到跨越門檻','Observed threshold crossings'],
    pending:['等待滿 48 小時','Waiting for 48 hours'], unreviewed:['已滿時限 · 待核實','Mature windows · unreviewed'],
    reviewed:['已核實事件','Reviewed windows'], uncertain_start:['起點不明 · 不納入','Unknown start · excluded'],
    reviewed_yes:['確認符合行動','Qualifying action confirmed'], reviewed_no:['完成核對 · 無符合行動','Reviewed · no qualifying action'],
    pendingStatus:['觀測中','Window pending'],
    cutoff:['資料截至','Data cutoff'], observations:['份快照','snapshots'],
    timeline:['查看事件與方法','Events and methodology'],
    methodology:['從首次觀測到跨越門檻起算 48 小時；持續高警戒不重複計次。取樣間隔超過 6 小時、過期或缺值後首次高警戒，列為起點不明。真實升級可能發生在兩次取樣之間。','Windows start at the first observed crossing, not the exact upstream transition. Sustained elevated readings count once. A high reading after a gap over 6 hours, stale data or missing data has an unknown start.'],
    scope:['本版重大行動：美軍直接跨國打擊、地面突擊或具名作戰的開端；例行部署、演習、聲明與持續反恐中的零星空襲不納入。定義或時間不明仍待核實，未找到新聞不等於沒有行動。','Scope: direct US interstate strikes, ground assaults or the opening of a named combat operation. Routine deployments, exercises, statements and isolated ongoing counterterrorism strikes are excluded. Ambiguous timing or scope remains unreviewed; no news found does not establish no action.'],
    caution:['兩組可能重疊，48 小時窗口也可能重疊，不能相加或當作獨立樣本。尚無對照期基準，不能宣稱預測有效或因果關係。','Groups and 48-hour windows may overlap; do not add them or treat them as independent samples. No control-period baseline is established, so predictive value and causation are unproven.'],
    source:['原始紀錄','Observation record'], sourceTime:['來源讀值時間','Source reading time'], end:['窗口結束','Window ends'],
    candidates:['待審核空襲紀錄（尚未計入）','Candidate strike records (not scored)'],
    mature:['成熟窗口符合行動比例','Qualifying-action fraction in mature windows'],
    interval:['95% 區間（未校正窗口重疊）','95% interval (not adjusted for overlapping windows)'],
    error:['部分封存無法讀取，比例暫停顯示','Some archives are unreadable; rate withheld']
  };
  const en=()=>window.WarhubI18n?.language==='en';
  const t=k=>words[k]?.[en()?1:0]||k;
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date=v=>{const n=new Date(v);return Number.isFinite(n.getTime())?n.toISOString().replace('T',' ').slice(0,16)+' UTC':'—';};
  function link(value){
    if(typeof value!=='string')return null;
    if(/^archives\/\d{4}\/\d{2}\/[a-zA-Z0-9_.-]+\.json\.gz$/.test(value))return 'https://github.com/virus11456/warhub/blob/main/'+value;
    try { const u=new URL(value);return u.protocol==='https:'&&['github.com','www.africom.mil'].includes(u.hostname)?u.href:null;}catch{return null;}
  }
  function draw(){
    const host=document.getElementById('pizza-backtest');if(!host)return;
    const open=host.querySelector('details')?.open;
    const g=report?.groups?.[threshold];
    const tabs=['3','2'].map(n=>`<button type="button" data-pizza-threshold="${n}" aria-pressed="${n===threshold}">${t(n==='3'?'broad':'strict')}</button>`).join('');
    let body=`<p>${t('loading')}</p>`;
    if(g){
      const counts=g.counts||{};
      const stat=(n,k)=>`<div><strong>${Number.isInteger(n)&&n>=0?n:'—'}</strong><span>${t(k)}</span></div>`;
      const rate=typeof g.rate==='number'&&Number.isFinite(g.rate)&&g.rate>=0&&g.rate<=1&&!report.unreadable_archives?g.rate:null;
      const events=(g.events||[]).slice().reverse().map(e=>{
        const href=link(e.archive);
        return `<li><div><time>${date(e.at)}</time><b>${esc(t(e.status==='pending'?'pendingStatus':e.status))}</b></div><small>DEFCON ${esc(e.level)} · ${t('sourceTime')}: ${date(e.source_at)} · ${t('end')}: ${date(e.ends_at)}</small>${href?` <a href="${esc(href)}" target="_blank" rel="noopener">${t('source')} ↗</a>`:''}</li>`;
      }).join('');
      body=`<div class="pizza-study-main"><div class="pizza-study-rate"><strong>${rate===null?'—':(rate*100).toFixed(1)+'%'}</strong><span>${t(rate===null?'rate':'mature')}</span></div><div class="pizza-study-stats">${stat(g.detected_crossings,'crossings')}${stat(counts.pending,'pending')}${stat(counts.unreviewed,'unreviewed')}${stat(g.reviewed,'reviewed')}</div></div><p class="pizza-study-cutoff">${t('cutoff')}: ${date(report.as_of)} · ${esc(report.observations)} ${t('observations')}${report.unreadable_archives?' · '+t('error'):''}</p><details ${open?'open':''}><summary>${t('timeline')}</summary><p>${t('methodology')}</p><p>${t('scope')}</p><p>${t('caution')}</p><p>${t('uncertain_start')}: ${esc(counts.uncertain_start??0)}</p><ol>${events}</ol><p>${t('candidates')}</p>${(report.candidate_actions||[]).map(a=>{const href=link(a.source);return href?`<a href="${esc(href)}" target="_blank" rel="noopener">${esc(a.date)} · AFRICOM ↗</a>`:'';}).join(' · ')}</details>`;
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
