const test=require('node:test'),assert=require('node:assert/strict');
const {build}=require('../cross-context.js');
const now=Date.parse('2026-09-15T00:00:00Z');
const market=(delta,extra={})=>({question:'Different contract?',slug:'fixture',delta_pp:delta,yes_percent:20,comparison_at:'2026-09-14T00:00:00Z',end_date:'2026-10-01T00:00:00Z',...extra});
const data=markets=>({taiwan_insight:{as_of:new Date(now).toISOString(),markets,activity:{status:'elevated'}}});
test('ranks absolute contract movement without assuming YES means escalation',()=>{
 const d=data([market(3),market(-8),market(90,{end_date:'2026-09-01T00:00:00Z'}),market(20,{comparison_at:null})]);
 const before=JSON.stringify(d),r=build(d,now);
 assert.equal(r.market.delta_pp,-8);assert.equal(r.comparable,2);assert.equal(JSON.stringify(d),before);
});
test('retains real zero movement but rejects stale, future and missing comparison data',()=>{
 assert.equal(build(data([market(0)]),now).market.delta_pp,0);
 assert.equal(build(data([market(null)]),now).market,null);
 assert.equal(build(data([]),now+6*3600000).fresh,false);
 assert.equal(build(data([]),now-1).fresh,false);
});
test('a 40/600 sample with zero candidates is partial, not zero notices',()=>{
 const d=data([]);d.notams={taiwan:{provider:'NOTAC',stale:true,observed_at:'2020-01-01T00:00:00Z',latest_attempt:{partial:true,complete:false,sample_count:40,reported_count:600,sample_danger:0,fetched_at:new Date(now).toISOString()}}};
 const r=build(d,now).notac;assert.equal(r.status,'partial');assert.equal(r.reported,600);assert.equal(r.danger,0);
 d.notams.taiwan.latest_attempt.sample_count=null;assert.equal(build(d,now).notac.status,'unavailable');
 d.notams.taiwan.provider='FAA';assert.equal(build(d,now).notac.status,'unavailable');
});
