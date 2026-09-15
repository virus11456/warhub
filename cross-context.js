/* Pure display analysis. No network, storage, scoring, or notifications. */
(function(root){
 'use strict';
 const timestamp=s=>typeof s==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(s)?Date.parse(s):NaN;
 const count=n=>Number.isInteger(n)&&n>=0;
 function build(snapshot,now=Date.now()){
  const v=snapshot?.taiwan_insight||{},at=timestamp(v.as_of);
  const out={fresh:Number.isFinite(at)&&now>=at&&now-at<6*3600000,market:null,comparable:0,notac:{status:'unavailable'}};
  if(!out.fresh)return out;
  out.activity=(v.activity||{}).status||'missing';
  const comparable=(v.markets||[]).filter(m=>{
   const before=timestamp(m.comparison_at),end=timestamp(m.end_date),hours=(at-before)/3600000;
   return Number.isFinite(m.delta_pp)&&Math.abs(m.delta_pp)<=100&&Number.isFinite(m.yes_percent)&&m.yes_percent>=0&&m.yes_percent<=100
    &&hours>=20&&hours<=28&&end>now&&typeof m.question==='string'&&typeof m.slug==='string';
  });
  out.comparable=comparable.length;
  out.market=comparable.reduce((best,m)=>!best||Math.abs(m.delta_pp)>Math.abs(best.delta_pp)?m:best,null);
  const n=snapshot.notams?.taiwan;
  if(n?.provider!=='NOTAC')return out;
  const a=n.stale?n.latest_attempt:n;
  const fetched=timestamp(a?.fetched_at),age=now-fetched;
  if(!Number.isFinite(age)||age<0||age>=6*3600000){out.notac.status='stale';return out;}
  if(!count(a.sample_count)||!count(a.reported_count)||a.sample_count>a.reported_count)return out;
  out.notac={status:a.complete===true?'complete':'partial',sample:a.sample_count,reported:a.reported_count,at:a.fetched_at,
   danger:count(a.sample_danger)&&a.sample_danger<=a.sample_count?a.sample_danger:null};
  return out;
 }
 const api={build};if(typeof module==='object'&&module.exports)module.exports=api;else root.WarhubCrossContext=api;
})(typeof window!=='undefined'?window:globalThis);
